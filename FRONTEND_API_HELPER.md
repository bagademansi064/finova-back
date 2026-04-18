# Finova Backend APIs & WebSockets - Frontend Helper Docs

This document serves as the absolute source-of-truth reference for the Frontend engineering team. The entire backend is built locally using Django and Django Rest Framework (DRF), and all real-time functionality runs locally via Django Channels.

**Base URL Context:**
- **Local:** `http://localhost:8001` or `http://0.0.0.0:8001`
- **WS Base:** `ws://localhost:8001`

---

## 1. Authentication (JWT)

We use robust `djangorestframework-simplejwt` for securing endpoints. 

### Register a User
- **Method:** `POST`
- **Endpoint:** `/api/users/register/`
- **Payload:** `{"username": "johndoe", "email": "john@example.com", "password": "...", "pancard_number": "ABCDE1234F"}`
- **Response:** Returns the newly created user data, their generated `finova_id` (e.g. `FHT928`), and their trust score.

### Login
- **Method:** `POST`
- **Endpoint:** `/api/users/login/`
- **Payload:** `{"finova_id": "FHT928", "password": "..."}`
- **Response:** Returns `{ "refresh": "...", "access": "..." }`.

> **Note:** For all subsequent protected API requests, inject `Authorization: Bearer <access_token>` in your HTTP headers.

---

## 2. Real-Time WebSockets (Chat & Groups)

All chat functionality operates completely off local WebSockets, ensuring lightning-fast messaging without third-party services. To authenticate a WebSocket, append the JWT to the query parameter: `?token=<jwt_access_token>`.

### 1-on-1 Direct Messaging
- **URL:** `ws://localhost:8001/ws/chat/<conversation_id>/?token=<jwt_token>`
- **Payload out (Send JSON):** `{"content": "Hello there!"}`
- **Payload in (Receive JSON):** 
```json
{
  "type": "chat_message_broadcast",
  "id": "uuid",
  "content": "Hello there!",
  "sender_finova_id": "FHT928"
}
```

### Community / Group Chat
- **URL:** `ws://localhost:8001/ws/groups/<group_id>/?token=<jwt_token>`
- **Behavior:** The backend automatically verifies if the user is an active member of this group. If they aren't, the socket actively rejects them. Same payloads as 1-on-1 apply.

---

## 3. Real-Time Market Data & Fundamentals (Yahoo Finance)

The backend handles `yfinance` caching. **Never query Yahoo Finance directly from React**, as they will ban the client IP. Instead, ping your custom API.

### Search / Retrieve Stocks
- **Method:** `GET`
- **Endpoint:** `/api/market/live/?symbols=RELIANCE,TCS,ZOMATO`
- **Behavior:** The backend stores 20 massive NIFTY 50 blue chips by default. If a user searches for a stock *not* in the database (e.g., ZOMATO), the backend synchronously intercepts it, pulls it instantly from Yahoo, caches it, and returns the Zerodha-style JSON layout.

**Response Structure (Zerodha-Style):**
```json
{
    "TCS.NS": {
        "symbol": "TCS.NS",
        "current_price": "2576.89",
        "percent_change": "0.86",
        "market_cap": 8788414431232,
        "pe_ratio": 17.51,
        "dividend_yield": 0.0343,
        "sector": "Technology",
        "industry": "Information Technology Services",
        "news_data": [ ... ],
        "last_updated": "..."
    }
}
```

---

## 4. Investment Groups & Voting Pipelines

The Micro-Investment App is structurally categorized into `Groups`, `Discussions`, and `Trade Polls`.

### Create a Group
- **Method:** `POST`
- **Endpoint:** `/api/groups/`
- **Payload:** `{"name": "Tech Bulls", "description": "...", "guidelines": "..."}`

### Create a Trade Proposal
- **Method:** `POST`
- **Endpoint:** `/api/groups/<group_id>/discussions/`
- **Payload:** `{"stock_symbol": "AAPL", "discussion_type": "buy", "reasoning": "...", "required_capital": "1000.00"}`

### Vote on a Proposal
- **Method:** `POST`
- **Endpoint:** `/api/groups/<group_id>/discussions/<discussion_id>/vote/`
- **Payload:** `{"choice": "buy"}` (or `"sell"`, `"hold"`)

> **Turbo-Reduction Feature:** If 100% of the active group members cast their votes on an active Trade Poll, the backend server mathematically collapses the remaining voting window by **95%** instantly.

> **Voting Ledger (Atomic Execution):**
> - **Buy Proposals:** A successful 60%+ 'buy' outcome automatically deducts the proposed `required_capital` from the group's pooled capital (`GroupWallet`) and records a `trade_buy` ledger transaction.
> - **Sell Proposals:** A successful 60%+ 'sell' outcome automatically credits the `required_capital` (as estimated proceeds) back to the group's pool and records a `trade_sell` ledger transaction. `Sell` proposals are entirely exempt from the "insufficient funds" (`requires_additional_funding`) gating mechanism.
