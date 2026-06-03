# Staging Smoke Checklist

Use this checklist after deploy with real credentials and seeded test accounts.

## Infra
- `backend-api` responds `200` on `/api/v1/internal/health`
- `backend-api` responds `200` on `/api/v1/internal/ready`
- `tg-service` responds `200` on `/health`
- Redis and Postgres containers are healthy
- FAQ index directory exists and backend startup completed without `readiness_failed`

## Telegram
- Linked student can open mini app and bootstrap without errors
- Linked teacher can run `/lessons`, `/qr`, `/attendance`, `/reasons`, `/broadcast`
- Unlinked Telegram user receives binding instructions
- Pending Telegram user receives pending-status guidance
- Rejected Telegram user receives re-apply guidance

## FAQ / AI
- One FAQ query returns a grounded answer from OpenRouter
- FAQ edit in Web Admin triggers index rebuild and updated answer is visible in Telegram
- If FAQ/OpenRouter temporarily fails, backend logs the degradation and the user gets a safe fallback

## Frontend Logging
- Forced runtime error in `student-app` appears in backend logs as `client_error_report`
- Forced runtime error in `web-admin` appears in backend logs as `client_error_report`
- Log payload contains `app`, `url`, `correlation_id`, sanitized `context`

## Backend Logging
- One forced backend `500` produces structured `internal_exception` log
- One unauthorized/service-token failure produces `http_exception` or `request_completed` warning log
- tg-service to backend calls log `tg_backend_request` and `tg_backend_response`
