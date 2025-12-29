# 🏦 MCP Banking Server

A production-ready banking server built with **FastMCP** (Model Context Protocol) featuring modern API design patterns, real-time updates, and enterprise-grade features.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔐 **API Key Authentication** | Secure endpoints with `X-API-Key` header |
| 🔄 **Idempotency Support** | Prevent duplicate transactions with `Idempotency-Key` |
| 📡 **WebSocket Updates** | Real-time transaction notifications |
| 📊 **CSV Export** | Stream transaction history as CSV |
| 📚 **OpenAPI Docs** | Auto-generated Swagger UI at `/docs` |
| 🐳 **Docker Ready** | One-command containerized deployment |
| 🤖 **MCP Integration** | LLM-compatible tools for AI assistants |

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- pip or uv package manager

### Installation

```bash
# Clone or navigate to the project directory
cd mcp

# Install dependencies
pip install -r requirements.txt
```

### Run the Server

```bash
# Start the server
python server.py

# Or use uvicorn directly
uvicorn server:app --reload --port 8000
```

The server will start and display:
- 🔑 Your default API key (save this!)
- 📚 API documentation URL

### Access the API

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 🔑 Authentication

All endpoints (except health check and root) require an API key.

Include the `X-API-Key` header in your requests:

```bash
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/accounts/1234567890
```

The default API key is displayed when the server starts.

### Disabling Authentication (for Demo/Testing)

To run the server without authentication (useful for demos or when being scanned by other services):

```bash
# Windows PowerShell
$env:DISABLE_AUTH="true"; python server.py

# Windows CMD
set DISABLE_AUTH=true && python server.py

# Linux/Mac
DISABLE_AUTH=true python server.py
```

When disabled, all endpoints become publicly accessible without needing the `X-API-Key` header.

## 📖 API Reference

### Accounts

#### Create Account
```bash
curl -X POST http://localhost:8000/accounts \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"holder_name": "John Doe"}'
```

#### Get Account Details
```bash
curl http://localhost:8000/accounts/1234567890 \
  -H "X-API-Key: YOUR_API_KEY"
```

### Transactions

#### Deposit (with idempotency)
```bash
curl -X POST http://localhost:8000/accounts/1234567890/deposit \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-key-123" \
  -d '{"amount": 100.00}'
```

#### Withdraw
```bash
curl -X POST http://localhost:8000/accounts/1234567890/withdraw \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"amount": 50.00}'
```

#### Get Transaction History
```bash
curl "http://localhost:8000/accounts/1234567890/transactions?limit=20" \
  -H "X-API-Key: YOUR_API_KEY"
```

#### Export Transactions as CSV
```bash
curl http://localhost:8000/accounts/1234567890/transactions/export \
  -H "X-API-Key: YOUR_API_KEY" \
  -o transactions.csv
```

## 📡 WebSocket Live Updates

Connect to receive real-time transaction notifications:

```javascript
// Browser JavaScript example
const ws = new WebSocket('ws://localhost:8000/ws/transactions/1234567890');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Transaction update:', data);
};

ws.onopen = () => {
  console.log('Connected to transaction updates');
};
```

### WebSocket Message Types

```json
// Connection established
{"type": "connected", "message": "Connected to transaction updates", "account_number": "1234567890"}

// Transaction notification
{"type": "transaction", "data": {"id": 1, "type": "DEPOSIT", "amount": 100.0, ...}}

// Ping response
{"type": "pong"}
```

## 🤖 MCP Tools

For LLM integration, the following MCP tools are available:

| Tool | Description |
|------|-------------|
| `create_account` | Create a new bank account |
| `deposit` | Add funds to an account |
| `withdraw` | Remove funds from an account |
| `get_balance` | Check account balance |
| `get_transaction_history` | View recent transactions |

### Using with FastMCP CLI

```bash
# Run in MCP mode
fastmcp run server.py:mcp --transport http --port 8000

# Development mode with inspector
fastmcp dev server.py:mcp
```

## 🐳 Docker Deployment

### Build and Run

```bash
# Build the image
docker build -t mcp-banking-server .

# Run the container
docker run -d -p 8000:8000 --name banking-server mcp-banking-server
```

### Docker Compose (optional)

```yaml
version: '3.8'
services:
  banking-server:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

## 📁 Project Structure

```
mcp/
├── server.py              # Main FastMCP server with MCP tools & REST API
├── database.py            # SQLite database operations
├── auth.py                # API key authentication
├── websocket_manager.py   # WebSocket connection management
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container configuration
├── README.md              # This file
└── bank.db                # SQLite database (created at runtime)
```

## 🔄 Idempotency

The `deposit` and `withdraw` endpoints support idempotency to prevent duplicate transactions:

1. Include an `Idempotency-Key` header with a unique identifier
2. If the same key is used again within 24 hours, the original response is returned
3. The `idempotent_replay: true` flag indicates a cached response

```bash
# First request - processes the transaction
curl -X POST ... -H "Idempotency-Key: txn-abc-123" -d '{"amount": 100}'

# Second request with same key - returns cached response
curl -X POST ... -H "Idempotency-Key: txn-abc-123" -d '{"amount": 100}'
# Response includes: "idempotent_replay": true
```

## 🛡️ Security Features

- **API Key Authentication**: All sensitive endpoints protected
- **Non-root Docker User**: Container runs as unprivileged user
- **Input Validation**: Pydantic models validate all inputs
- **SQL Injection Prevention**: Parameterized queries throughout

## 📝 License

MIT License - Feel free to use and modify for your projects.

---

Built with ❤️ using [FastMCP](https://gofastmcp.com)
