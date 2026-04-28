// People routes - Speaker voice profiles for transcript naming

use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};
use serde_json::json;
use std::collections::HashMap;

use crate::auth::AuthUser;
use crate::models::{BulkAssignSegmentsRequest, CreatePersonRequest, Person, TranscriptSegment};
use crate::AppState;

/// Create people routes
pub fn people_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/users/people", get(get_people).post(create_person))
        .route(
            "/v1/users/people/:person_id",
            axum::routing::delete(delete_person),
        )
        .route(
            "/v1/users/people/:person_id/name",
            axum::routing::patch(update_person_name),
        )
        .route(
            "/v1/conversations/:conversation_id/segments/assign-bulk",
            axum::routing::patch(assign_segments_bulk),
        )
}

/// GET /v1/users/people - Get all people for the user
async fn get_people(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<Vec<Person>>, StatusCode> {
    match state.firestore.get_people(&user.uid).await {
        Ok(people) => Ok(Json(people)),
        Err(e) => {
            tracing::error!("Failed to get people: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/users/people - Create a new person
async fn create_person(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreatePersonRequest>,
) -> Result<Json<Person>, StatusCode> {
    if request.name.trim().is_empty() {
        return Err(StatusCode::BAD_REQUEST);
    }

    match state.firestore.create_person(&user.uid, &request.name).await {
        Ok(person) => Ok(Json(person)),
        Err(e) => {
            tracing::error!("Failed to create person: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/users/people/:person_id/name?value=NewName - Update a person's name
async fn update_person_name(
    State(state): State<AppState>,
    user: AuthUser,
    Path(person_id): Path<String>,
    axum::extract::Query(query): axum::extract::Query<NameQuery>,
) -> StatusCode {
    if query.value.trim().is_empty() {
        return StatusCode::BAD_REQUEST;
    }

    match state
        .firestore
        .update_person_name(&user.uid, &person_id, &query.value)
        .await
    {
        Ok(()) => StatusCode::OK,
        Err(e) => {
            tracing::error!("Failed to update person name: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

/// DELETE /v1/users/people/:person_id - Delete a person
async fn delete_person(
    State(state): State<AppState>,
    user: AuthUser,
    Path(person_id): Path<String>,
) -> StatusCode {
    match state.firestore.delete_person(&user.uid, &person_id).await {
        Ok(()) => StatusCode::NO_CONTENT,
        Err(e) => {
            tracing::error!("Failed to delete person: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

/// PATCH /v1/conversations/:conversation_id/segments/assign-bulk
async fn assign_segments_bulk(
    State(state): State<AppState>,
    user: AuthUser,
    Path(conversation_id): Path<String>,
    Json(request): Json<BulkAssignSegmentsRequest>,
) -> StatusCode {
    if request.assign_type != "is_user" && request.assign_type != "person_id" {
        return StatusCode::BAD_REQUEST;
    }

    let segment_ids = request.segment_ids.clone();
    let assign_type = request.assign_type.clone();
    let value = request.value.clone();

    match state
        .firestore
        .assign_segments_bulk(
            &user.uid,
            &conversation_id,
            &segment_ids,
            &assign_type,
            value.as_deref(),
        )
        .await
    {
        Ok(()) => {
            if state.config.omi_speaker_refinement_url.is_some() {
                let state_clone = state.clone();
                let user_clone = user.clone();
                let conversation_id_clone = conversation_id.clone();
                tokio::spawn(async move {
                    if let Err(e) = post_speaker_refinement(
                        state_clone,
                        user_clone,
                        conversation_id_clone,
                        segment_ids,
                    )
                    .await
                    {
                        tracing::warn!("Speaker refinement webhook failed: {}", e);
                    }
                });
            }
            StatusCode::OK
        }
        Err(e) => {
            tracing::error!("Failed to assign segments: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

fn segment_target_matches(seg: &TranscriptSegment, idx: usize, target: &str) -> bool {
    if let Some(index) = target
        .strip_prefix("#index:")
        .and_then(|value| value.parse::<usize>().ok())
    {
        return index == idx;
    }
    seg.id.as_deref() == Some(target)
}

async fn post_speaker_refinement(
    state: AppState,
    user: AuthUser,
    conversation_id: String,
    segment_ids: Vec<String>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let Some(url) = state.config.omi_speaker_refinement_url.clone() else {
        return Ok(());
    };

    let conversation = state
        .firestore
        .get_conversation(&user.uid, &conversation_id)
        .await?
        .ok_or_else(|| {
            std::io::Error::new(
                std::io::ErrorKind::NotFound,
                "Conversation not found after segment assignment",
            )
        })?;

    let people = state.firestore.get_people(&user.uid).await.unwrap_or_default();
    let people_by_id: HashMap<String, String> = people
        .into_iter()
        .map(|person| (person.id, person.name))
        .collect();
    let user_name = user.name.clone().unwrap_or_else(|| "Ryan".to_string());

    let segments: Vec<serde_json::Value> = conversation
        .transcript_segments
        .iter()
        .enumerate()
        .filter(|(idx, seg)| {
            segment_ids
                .iter()
                .any(|target| segment_target_matches(seg, *idx, target))
        })
        .map(|(_, seg)| {
            let person_name = if seg.is_user {
                user_name.clone()
            } else {
                seg.person_id
                    .as_ref()
                    .and_then(|person_id| people_by_id.get(person_id))
                    .cloned()
                    .unwrap_or_default()
            };
            json!({
                "id": seg.id.clone(),
                "text": seg.text.clone(),
                "speaker": seg.speaker.clone(),
                "speaker_id": seg.speaker_id,
                "is_user": seg.is_user,
                "person_id": seg.person_id.clone(),
                "person_name": person_name,
                "start": seg.start,
                "end": seg.end
            })
        })
        .collect();

    if segments.is_empty() {
        return Ok(());
    }

    let payload = json!({
        "source": "omi_local",
        "conversation_id": conversation_id,
        "user_id": user.uid,
        "user_name": user_name,
        "started_at": conversation.started_at.to_rfc3339(),
        "people": people_by_id.clone(),
        "segments": segments,
    });

    let response = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()?
        .post(url)
        .json(&payload)
        .send()
        .await?;

    if !response.status().is_success() {
        return Err(format!("refinement webhook HTTP {}", response.status()).into());
    }
    Ok(())
}

#[derive(serde::Deserialize)]
struct NameQuery {
    value: String,
}
