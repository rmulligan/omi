"""
Agentic chat system using OpenAI-compatible tool use.

This module implements a tool-calling agent that autonomously decides which tools
to use to gather context and answer user questions. Uses LangChain's ChatOpenAI
with bind_tools for real-time streaming responses.
"""

import uuid
import asyncio
import contextvars
import traceback
from typing import List, Optional, AsyncGenerator, Any, Tuple

import os

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

# Context variable to store config for tools
agent_config_context: contextvars.ContextVar[dict] = contextvars.ContextVar('agent_config', default=None)

from models.app import App
from models.chat import Message, ChatSession, PageContext
from utils.retrieval.tools import (
    get_conversations_tool,
    search_conversations_tool,
    get_memories_tool,
    search_memories_tool,
    get_action_items_tool,
    create_action_item_tool,
    update_action_item_tool,
    get_omi_product_info_tool,
    get_calendar_events_tool,
    create_calendar_event_tool,
    update_calendar_event_tool,
    delete_calendar_event_tool,
    get_gmail_messages_tool,
    get_apple_health_steps_tool,
    get_apple_health_sleep_tool,
    get_apple_health_heart_rate_tool,
    get_apple_health_workouts_tool,
    get_apple_health_summary_tool,
    search_files_tool,
    manage_daily_summary_tool,
    create_chart_tool,
    get_screen_activity_tool,
    search_screen_activity_tool,
    save_user_preference_tool,
)
from utils.retrieval.tools.app_tools import load_app_tools, get_tool_status_message
from utils.retrieval.safety import AgentSafetyGuard, SafetyGuardError
from utils.llm.chat import _get_agentic_qa_prompt
from utils.llm.usage_tracker import get_usage_callback
import logging

# Import langsmith traceable if available
try:
    from langsmith import traceable as _traceable
except ImportError:

    def _traceable(**kwargs):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)

_usage_callback = get_usage_callback()


def _openai_compatible_base_url(base_url: str) -> str:
    base = base_url.rstrip('/')
    return base if base.endswith('/v1') else f'{base}/v1'


# PROMPT CACHE OPTIMIZATION: This list MUST stay fixed and in this exact order.
# Tools are bound to the ChatOpenAI instance so they're included in the request.
# Dynamic per-user app tools are appended to CORE_TOOLS before binding.
CORE_TOOLS = [
    get_conversations_tool,
    search_conversations_tool,
    get_memories_tool,
    search_memories_tool,
    get_action_items_tool,
    create_action_item_tool,
    update_action_item_tool,
    get_omi_product_info_tool,
    get_calendar_events_tool,
    create_calendar_event_tool,
    update_calendar_event_tool,
    delete_calendar_event_tool,
    get_gmail_messages_tool,
    get_apple_health_steps_tool,
    get_apple_health_sleep_tool,
    get_apple_health_heart_rate_tool,
    get_apple_health_workouts_tool,
    get_apple_health_summary_tool,
    search_files_tool,
    manage_daily_summary_tool,
    create_chart_tool,
    get_screen_activity_tool,
    search_screen_activity_tool,
    save_user_preference_tool,
]

# Standard tool names (used to detect app tools by exclusion)
STANDARD_TOOL_NAMES = {t.name for t in CORE_TOOLS}


def get_tool_display_name(tool_name: str, tool_obj: Optional[Any] = None) -> str:
    """Convert tool name to user-friendly display name."""
    # Check global mapping from app_tools first
    status_msg = get_tool_status_message(tool_name)
    if status_msg:
        return status_msg

    # Check tool object for custom status_message
    if tool_obj and hasattr(tool_obj, 'status_message') and tool_obj.status_message:
        return tool_obj.status_message

    tool_display_map = {
        'get_calendar_events_tool': 'Checking calendar',
        'create_calendar_event_tool': 'Creating calendar event',
        'update_calendar_event_tool': 'Updating calendar event',
        'delete_calendar_event_tool': 'Deleting calendar event',
        'get_gmail_messages_tool': 'Checking Gmail',
        'web_search': 'Searching the web',
        'get_conversations_tool': 'Searching conversations',
        'search_conversations_tool': 'Searching conversations',
        'get_memories_tool': 'Searching memories',
        'search_memories_tool': 'Searching memories',
        'get_action_items_tool': 'Checking action items',
        'create_action_item_tool': 'Creating action item',
        'update_action_item_tool': 'Updating action item',
        'get_omi_product_info_tool': 'Looking up product info',
        'manage_daily_summary_tool': 'Updating notification settings',
        'create_chart_tool': 'Creating chart',
        'get_screen_activity_tool': 'Checking screen activity',
        'search_screen_activity_tool': 'Searching screen activity',
        'save_user_preference_tool': 'Saving preference',
    }

    if tool_name in tool_display_map:
        return tool_display_map[tool_name]

    if 'calendar' in tool_name.lower():
        return 'Checking calendar'
    elif 'web_search' in tool_name.lower():
        return 'Searching the web'
    elif 'memory' in tool_name.lower():
        return 'Searching memories'
    elif 'conversation' in tool_name.lower():
        return 'Searching conversations'
    elif 'action' in tool_name.lower():
        return 'Checking action items'

    return tool_name.replace('_', ' ').title()


class AsyncStreamingCallback:
    """Callback for streaming LLM responses with data and thought prefixes."""

    def __init__(self):
        self.queue = asyncio.Queue()

    async def put_data(self, text):
        await self.queue.put(f"data: {text}")

    async def put_thought(self, text, app_id: Optional[str] = None):
        if app_id:
            await self.queue.put(f"think: {text}|app_id:{app_id}")
        else:
            await self.queue.put(f"think: {text}")

    def put_thought_nowait(self, text, app_id: Optional[str] = None):
        if app_id:
            self.queue.put_nowait(f"think: {text}|app_id:{app_id}")
        else:
            self.queue.put_nowait(f"think: {text}")

    def put_data_nowait(self, text):
        self.queue.put_nowait(f"data: {text}")

    async def end(self):
        await self.queue.put(None)

    def end_nowait(self):
        self.queue.put_nowait(None)


# ---------------------------------------------------------------------------
# Message format conversion
# ---------------------------------------------------------------------------


def _messages_to_openai(messages: List[Message]) -> list:
    """Convert chat messages to OpenAI API format."""
    openai_messages = []
    for msg in messages:
        role = "assistant" if msg.sender == "ai" else "user"
        openai_messages.append({"role": role, "content": msg.text})
    return openai_messages


# ---------------------------------------------------------------------------
# Core OpenAI agent streaming loop
# ---------------------------------------------------------------------------


async def _run_openai_agent_stream(
    system_prompt: str,
    messages: list,
    tools: list,
    tool_registry: dict,
    callback: AsyncStreamingCallback,
    full_response: list,
    safety_guard: AgentSafetyGuard,
    configurable: dict,
    llm: ChatOpenAI,
):
    """Run the OpenAI tool-use loop with streaming.

    This replaces the Anthropic native tool-use loop with a simple
    while loop that calls ChatOpenAI with bind_tools, executes any
    tool calls, and feeds results back until the model stops requesting tools.
    """
    loop_iteration = 0

    while True:
        loop_iteration += 1
        first_text_in_iteration = True

        try:
            # Bind tools to the LLM and stream
            llm_with_tools = llm.bind_tools(tools)
            async for chunk in llm_with_tools.astream(
                [
                    {"role": "system", "content": system_prompt},
                    *messages,
                ]
            ):
                if hasattr(chunk, 'content') and chunk.content:
                    # Add separator between loop iterations so text doesn't run together
                    if first_text_in_iteration and loop_iteration > 1 and full_response:
                        last_char = full_response[-1][-1] if full_response[-1] else ''
                        first_char = chunk.content[0] if chunk.content else ''
                        if (
                            last_char
                            and first_char
                            and last_char not in (' ', '\n')
                            and first_char not in (' ', '\n')
                        ):
                            full_response.append('\n\n')
                            await callback.put_data('\n\n')
                    first_text_in_iteration = False
                    full_response.append(chunk.content)
                    await callback.put_data(chunk.content)

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            await callback.put_data(f"\n\nSorry, I encountered an error. Please try again.")
            await callback.end()
            return

        # Check for tool calls in the last chunk
        if not hasattr(chunk, 'tool_calls') or not chunk.tool_calls:
            break

        # Execute tool calls
        tool_results = []
        for tool_call in chunk.tool_calls:
            tool_name = tool_call.get('name', '')
            tool_input = tool_call.get('args', {})
            tool_call_id = tool_call.get('id', '')

            # Safety guard: validate before execution
            try:
                safety_guard.validate_tool_call(tool_name, tool_input)
                warning = safety_guard.should_warn_user()
                if warning:
                    await callback.put_thought(warning)
            except SafetyGuardError as e:
                await callback.put_data(f"\n\n{str(e)}")
                logger.error(f"Safety Guard blocked tool call: {e}")
                await callback.end()
                return

            # Execute tool
            try:
                result = await _execute_tool(tool_name, tool_input, tool_registry, configurable)
            except Exception as e:
                logger.error(f"Tool execution error ({tool_name}): {e}")
                result = f"Error executing tool: {str(e)}"

            logger.info(f"Tool ended: {tool_name}")

            # Calendar status messages
            await _emit_calendar_status(callback, tool_name, result)

            # Safety guard: check context size after execution
            try:
                safety_guard.check_context_size(result)
            except SafetyGuardError as e:
                await callback.put_data(f"\n\n{str(e)}")
                logger.error(f"Safety Guard blocked due to context size: {e}")
                await callback.end()
                return

            tool_results.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tool_call_id,
                    "name": tool_name,
                    "args": tool_input,
                }],
            })
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result,
            })

        messages.extend(tool_results)

    # Log final safety guard stats
    stats = safety_guard.get_stats()
    logger.info(f"Safety Guard final stats: {stats}")


# ---------------------------------------------------------------------------
# Tool schema conversion: LangChain @tool -> OpenAI tool format
# ---------------------------------------------------------------------------


def _langchain_tool_to_openai(lc_tool, defer_loading: bool = False) -> dict:
    """Convert a LangChain @tool to OpenAI tool schema format."""
    schema = lc_tool.args_schema.schema()
    properties = {k: v for k, v in schema.get('properties', {}).items() if k != 'config'}
    required = [r for r in schema.get('required', []) if r != 'config']

    tool_def = {
        "type": "function",
        "function": {
            "name": lc_tool.name,
            "description": lc_tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
    return tool_def


# ---------------------------------------------------------------------------
# App ID extraction for non-standard tools
# ---------------------------------------------------------------------------


def _extract_app_id(tool_name: str) -> Optional[str]:
    """Extract app_id from an app tool name (format: appid_toolname)."""
    if tool_name not in STANDARD_TOOL_NAMES and '_' in tool_name:
        parts = tool_name.split('_', 1)
        if len(parts) == 2:
            return parts[0]
    return None


# ---------------------------------------------------------------------------
# Calendar tool status messages
# ---------------------------------------------------------------------------


async def _emit_calendar_status(callback: AsyncStreamingCallback, tool_name: str, output: str):
    """Emit calendar-specific completion status messages."""
    if 'calendar' not in tool_name.lower():
        return

    if 'create' in tool_name.lower():
        if output and ('Successfully created' in output or '✅' in output):
            await callback.put_thought('Event created successfully')
        elif output and ('Error' in output or 'error' in output.lower()):
            await callback.put_thought('Failed to create event')
        else:
            await callback.put_thought('Creating event...')
    elif 'update' in tool_name.lower():
        if output and ('Successfully updated' in output or '✅' in output):
            await callback.put_thought('Event updated successfully')
        elif output and ('Error' in output or 'error' in output.lower()):
            await callback.put_thought('Failed to update event')
        else:
            await callback.put_thought('Updating event...')
    elif 'delete' in tool_name.lower():
        if output and ('Successfully deleted' in output or '✅' in output):
            await callback.put_thought('Event deleted successfully')
        elif output and ('Error' in output or 'error' in output.lower()):
            await callback.put_thought('Failed to delete event')
        else:
            await callback.put_thought('Deleting event...')
    elif 'get' in tool_name.lower() or 'search' in tool_name.lower():
        if output and len(output) > 0:
            await callback.put_thought('Found calendar events')
        else:
            await callback.put_thought('No events found')


# ---------------------------------------------------------------------------
# Core tool execution
# ---------------------------------------------------------------------------


@_traceable(name="chat.tool_execution", run_type="tool")
async def _execute_tool(tool_name: str, tool_input: dict, registry: dict, configurable: dict) -> str:
    """Execute a LangChain tool by name, injecting RunnableConfig."""
    tool_obj = registry[tool_name]
    config = RunnableConfig(configurable=configurable)
    result = await tool_obj.ainvoke(tool_input, config=config)
    return str(result)


# ---------------------------------------------------------------------------
# Main agentic chat streaming entry point
# ---------------------------------------------------------------------------


@_traceable(name="chat.execute_agentic_chat_stream", run_type="chat")
async def execute_agentic_chat_stream(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
    callback_data: Optional[dict] = None,
    cited: bool = False,
    configurable: Optional[dict] = None,
) -> AsyncGenerator[str, None]:
    """Execute agentic chat using OpenAI-compatible tool use.

    This is the main entry point for agentic chat. It builds the system prompt,
    loads available tools, and runs the OpenAI tool-use loop.

    Args:
        uid: User ID
        messages: Chat messages
        app: Optional app context
        callback_data: Optional dict to store results
        cited: Whether to use cited mode
        configurable: Configurable parameters

    Yields:
        Streaming chunks (data: ..., think: ...)
    """
    configurable = configurable or {}
    conversations_collected = []

    system_prompt = _get_agentic_qa_prompt(
        cited=cited,
        app=app,
        message_history=messages,
        callback_data=callback_data,
    )

    # Build tool registry
    core_tools_list = list(CORE_TOOLS)
    app_tools = load_app_tools(uid, configurable) if callable(app) else []
    all_tools = core_tools_list + (app_tools or [])
    tool_registry = {t.name: t for t in all_tools}

    # Convert tools to OpenAI schema
    tool_schemas = [_langchain_tool_to_openai(t) for t in all_tools]

    # Safety guard
    safety_guard = AgentSafetyGuard()

    # Convert messages to OpenAI format
    openai_messages = _messages_to_openai(messages)

    # Build the LLM - uses LLM_BASE_URL if set (routes through Hermes agent)
    _local_url = os.environ.get('LLM_BASE_URL')
    _local_key = os.environ.get('LLM_API_KEY', '') or 'local'
    _local_model = os.environ.get('LLM_MODEL', 'magnum-opus:35b').strip() or 'magnum-opus:35b'
    llm_kwargs: dict[str, Any] = {
        'model': _local_model,
        'temperature': 0.7,
        'max_tokens': 8192,
        'streaming': True,
        'stream_options': {'include_usage': True},
        'callbacks': [_usage_callback],
    }
    if _local_url:
        llm_kwargs['base_url'] = _openai_compatible_base_url(_local_url)
        llm_kwargs['api_key'] = _local_key
    llm = ChatOpenAI(**llm_kwargs)

    callback = AsyncStreamingCallback()
    full_response = []

    # Run the agent stream
    task = asyncio.create_task(
        _run_openai_agent_stream(
            system_prompt,
            openai_messages,
            tool_schemas,
            tool_registry,
            callback,
            full_response,
            safety_guard,
            configurable,
            llm,
        )
    )

    # Stream from callback queue
    try:
        while True:
            chunk = await callback.queue.get()
            if chunk is None:
                break
            yield chunk

        await task

        # Store results in callback_data
        if callback_data is not None:
            callback_data['answer'] = ''.join(full_response)
            callback_data['memories_found'] = conversations_collected if conversations_collected else []
            callback_data['ask_for_nps'] = True  # Simplified
            logger.info(f"Agentic chat completed")

    except asyncio.CancelledError:
        task.cancel()
        raise
    except Exception as e:
        logger.error(f"Error in execute_agentic_chat_stream: {e}")
        traceback.print_exc()
        if callback_data is not None:
            callback_data['error'] = str(e)

    yield None  # Signal completion


# ---------------------------------------------------------------------------
# Re-export for backward compatibility
# ---------------------------------------------------------------------------

# Alias the old function name for callers that reference it
execute_anthropic_agent_stream = execute_agentic_chat_stream
execute_openai_agent_stream = execute_agentic_chat_stream
