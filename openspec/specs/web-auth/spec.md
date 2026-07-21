# Web Auth Specification

## Purpose

Authentication and session management for the DARTH-GAIN web dashboard. Provides user registration, login/logout, session-based auth via signed cookies, healthcheck, and static file serving. Each user gets an isolated SQLite database for workout data.

## Requirements

### Requirement: FastAPI app with lifecycle management

The system SHALL provide a FastAPI application that initializes on startup (creates connection pool, sets WAL mode) and cleans up on shutdown. The app SHALL serve under a configurable host/port with uvicorn.

#### Scenario: Startup creates tables and enables WAL

- GIVEN the FastAPI app starts
- WHEN the startup event fires
- THEN `users.db` is created with all tables, and `PRAGMA journal_mode=WAL` is set on every connection

#### Scenario: Graceful shutdown closes connections

- GIVEN the FastAPI app is running
- WHEN a shutdown signal is received
- THEN all database connections are closed cleanly

### Requirement: users.db schema for authentication

The system MUST create and manage a `users.db` SQLite database with a `users` table containing: `id` (INTEGER PK), `username` (TEXT UNIQUE NOT NULL), `password_hash` (TEXT NOT NULL), `hevy_api_key` (TEXT), and `created_at` (TEXT DEFAULT datetime('now')).

#### Scenario: Users table created on startup

- GIVEN no `users.db` exists
- WHEN the app starts for the first time
- THEN the `users` table is created with all required columns

#### Scenario: Duplicate username is rejected

- GIVEN a user "alice" exists in `users.db`
- WHEN a registration attempt for "alice" is made
- THEN the system returns a 409 Conflict error

### Requirement: Healthcheck endpoint

The system MUST expose `GET /health` returning a 200 JSON response with `{"status": "ok"}`. This endpoint SHALL NOT require authentication.

#### Scenario: Healthcheck returns ok

- GIVEN the app is running
- WHEN a client sends `GET /health`
- THEN the response is 200 with body `{"status": "ok"}`

#### Scenario: Healthcheck bypasses auth

- GIVEN no session cookie is present
- WHEN a client sends `GET /health`
- THEN the response is 200 (not redirected to login)

### Requirement: Static file serving

The system SHALL serve static assets (CSS, JS, favicon) from a `static/` directory via FastAPI's `StaticFiles` mount at `/static/`.

#### Scenario: Static file loads successfully

- GIVEN a file `static/app.css` exists
- WHEN a client requests `GET /static/app.css`
- THEN the response is 200 with the file contents

### Requirement: POST /login authenticates users

The system MUST accept `POST /login` with `application/x-www-form-urlencoded` body containing `username` and `password`. On success, it SHALL set a signed session cookie via `itsdangerous` and return a 302 redirect to `/`. On failure, it SHALL return a 401 with an error message.

#### Scenario: Successful login redirects to dashboard

- GIVEN a registered user "alice" with correct password
- WHEN the client sends `POST /login` with `username=alice&password=correct`
- THEN the response is 302 redirecting to `/` with a `session` cookie set

#### Scenario: Wrong password returns 401

- GIVEN a registered user "alice"
- WHEN the client sends `POST /login` with `username=alice&password=wrong`
- THEN the response is 401 and no session cookie is set

#### Scenario: Nonexistent user returns 401

- GIVEN no user "nobody" exists
- WHEN the client sends `POST /login` with `username=nobody&password=x`
- THEN the response is 401 with an error message (does not reveal whether user exists)

### Requirement: POST /logout destroys session

The system MUST accept `POST /logout` which clears the session cookie and redirects to the login page.

#### Scenario: Logout clears session

- GIVEN an authenticated session
- WHEN the client sends `POST /logout`
- THEN the response is 302 redirecting to `/login` and the session cookie is cleared

### Requirement: Auth middleware protects routes

The system MUST check the session cookie on every request to protected routes. If the cookie is missing, expired, or tampered with, the system SHALL redirect to `/login`. If valid, the middleware SHALL make the user's identity and DB connection available to handlers.

#### Scenario: Unauthenticated request redirects to login

- GIVEN no valid session cookie
- WHEN the client sends `GET /`
- THEN the response is 302 redirecting to `/login`

#### Scenario: Tampered cookie is rejected

- GIVEN a valid session cookie that was modified client-side
- WHEN the client sends `GET /` with the tampered cookie
- THEN the response is 302 redirecting to `/login`

#### Scenario: Expired cookie is rejected

- GIVEN a session cookie past its expiry time
- WHEN the client sends `GET /` with the expired cookie
- THEN the response is 302 redirecting to `/login`

### Requirement: User registration creates isolated database

The system MUST accept `POST /register` with `username`, `password`, and optional `hevy_api_key`. On success, a new user row is inserted into `users.db`, and a per-user SQLite database is created at `/data/user_{id}/workouts.db` with all tables.

#### Scenario: New user registration succeeds

- GIVEN no user "bob" exists
- WHEN the client sends `POST /register` with `username=bob&password=secure`
- THEN a 302 redirect to `/login` is returned, a user row is created with bcrypt-hashed password, and `/data/user_{id}/workouts.db` exists with all tables

#### Scenario: Registration with missing password returns 422

- GIVEN the client sends `POST /register` without a password
- WHEN the request is processed
- THEN the response is 422 with a validation error

### Requirement: Per-user database routing

The system MUST route each authenticated user's requests to their own `/data/user_{id}/workouts.db` file. The shared `users.db` is used only for authentication.

#### Scenario: Authenticated user accesses own database

- GIVEN user "alice" (id=1) is authenticated
- WHEN the dashboard handler processes `GET /`
- THEN it connects to `/data/user_1/workouts.db` (not the shared `users.db`)

#### Scenario: Two users see different data

- GIVEN user "alice" has exercises and user "bob" has none
- WHEN both log in and visit `/`
- THEN alice sees exercises and bob sees an empty state

## Edge Cases

- **bcrypt password hashing**: Passwords MUST be hashed with bcrypt before storage; never stored in plain text
- **Login timing**: Failed login attempts SHOULD NOT reveal whether the username exists vs. wrong password (same response time where practical)
- **Session theft**: Session cookie SHOULD have `HttpOnly`, `Secure` (in production), and `SameSite=Lax` flags
- **Registration with existing username**: Returns 409, not 500
- **Migration**: If a legacy `workouts.db` exists at the default path, the system SHOULD offer a one-time copy to the first registered user's directory (CLI unaffected)
