from datetime import datetime
from typing import Dict, List

from models.trend import Trend, valid_items
from ._client import db, document_id_from_seed
import logging

logger = logging.getLogger(__name__)


def _get_trends_from_local_db() -> List[Dict]:
    """Return trends data from the local DB."""
    try:
        trends_ref = db.collection('trends')
        trends_docs = [doc for doc in trends_ref.stream()]
        trends_data = []
        for category in trends_docs:
            try:
                category_data = category.to_dict()
                if category_data.get('category') not in [
                    'ceo', 'company', 'software_product',
                    'hardware_product', 'ai_product',
                ]:
                    continue
                topics_data = category_data.get('topics', [])
                cleaned_topics = []
                topics = sorted(topics_data, key=lambda e: len(e.get('memory_ids', [])), reverse=True)
                for topic in topics:
                    if topic.get('topic') not in valid_items:
                        continue
                    topic['memories_count'] = len(topic.get('memory_ids', []))
                    del topic['memory_ids']
                    cleaned_topics.append(topic)
                category_data['topics'] = cleaned_topics
                trends_data.append(category_data)
            except Exception as e:
                logger.error(e)
                continue
        return trends_data
    except Exception as e:
        logger.error(f'get_trends_data failed: {e}')
        return []


def get_trends_data() -> List[Dict]:
    return _get_trends_from_local_db()


def save_trends(memory_id: str, trends: List[Trend]):
    """Store trends in the local DB."""
    try:
        trends_coll_ref = db.collection('trends')
        for trend in trends:
            category = trend.category.value
            topics = trend.topics
            trend_type = trend.type.value
            category_id = document_id_from_seed(category + trend_type)
            category_doc_ref = trends_coll_ref.document(category_id)

            category_doc_ref.set(
                {
                    "id": category_id,
                    "category": category,
                    "type": trend_type,
                    "created_at": datetime.utcnow(),
                },
                merge=True,
            )

            topics_coll_ref = category_doc_ref.collection('topics')

            for topic in topics:
                topic_id = document_id_from_seed(topic)
                topic_doc_ref = topics_coll_ref.document(topic_id)

                existing = topic_doc_ref.get()
                if existing:
                    data = existing.to_dict()
                    memory_ids = data.get('memory_ids', [])
                    if memory_id not in memory_ids:
                        memory_ids.append(memory_id)
                    topic_doc_ref.set(
                        {"id": topic_id, "topic": topic, "memory_ids": memory_ids},
                        merge=True,
                    )
                else:
                    topic_doc_ref.set(
                        {"id": topic_id, "topic": topic, "memory_ids": [memory_id]}
                    )
    except Exception as e:
        logger.error(f'save_trends failed: {e}')
