"""
MCP Banking Server - Main Application

A production-ready banking server built with FastMCP featuring:
- MCP tools for LLM integration
- REST API endpoints with OpenAPI docs
- API key authentication
- Idempotency support for transactions
- WebSocket live transaction notifications
- CSV export for transaction history
"""

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse, PlainTextResponse
from starlette.websockets import WebSocket, WebSocketDisconnect
from typing import Optional
import asyncio
import csv
import io
import os

DISABLE_AUTH = os.environ.get("DISABLE_AUTH", "").lower() in ("true", "1", "yes")

from database import (
    init_database,
    create_account as db_create_account,
    get_account,
    get_account_by_id,
    update_balance,
    record_transaction,
    get_transactions,
    get_all_transactions,
    check_idempotency_key,
    store_idempotency_key,
    get_default_api_key,
    validate_api_key
)
from websocket_manager import manager

init_database()

mcp = FastMCP(
    name="MCP Banking Server",
    instructions="""
    A banking server that provides account management and transaction operations.
    
    Available operations:
    - Create new bank accounts
    - Deposit funds into accounts
    - Withdraw funds from accounts
    - Check account balance
    - View transaction history
    
    All monetary operations support idempotency to prevent double-processing.
    """
)


def verify_api_key(request: Request) -> bool:
    """Verify API key from request headers."""
    # Skip authentication if DISABLE_AUTH is set
    if DISABLE_AUTH:
        return True
    
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return False
    return validate_api_key(api_key)


def unauthorized_response(message: str = "Unauthorized") -> JSONResponse:
    """Return a 401 unauthorized response."""
    return JSONResponse(
        {"error": message, "detail": "Include valid 'X-API-Key' header"},
        status_code=401
    )


# Business Logic Functions 

def do_create_account(holder_name: str) -> dict:
    """Create a new bank account for a customer."""
    if not holder_name or len(holder_name.strip()) == 0:
        return {"success": False, "error": "Holder name is required"}
    
    result = db_create_account(holder_name.strip())
    return {
        "success": True,
        "message": f"Account created successfully for {holder_name}",
        "account": result
    }


def do_deposit(
    account_number: str,
    amount: float,
    idempotency_key: Optional[str] = None
) -> dict:
    """Deposit funds into a bank account."""
    if idempotency_key:
        cached = check_idempotency_key(idempotency_key)
        if cached:
            cached["idempotent_replay"] = True
            return cached
    
    if amount <= 0:
        return {"success": False, "error": "Amount must be positive"}
    
    account = get_account(account_number)
    if not account:
        return {"success": False, "error": f"Account {account_number} not found"}
    
    new_balance = account['balance'] + amount
    update_balance(account['id'], new_balance)
    
    transaction = record_transaction(
        account_id=account['id'],
        transaction_type="DEPOSIT",
        amount=amount,
        balance_after=new_balance,
        description=f"Deposit of ${amount:.2f}"
    )
    
    result = {
        "success": True,
        "message": f"Successfully deposited ${amount:.2f}",
        "transaction": transaction,
        "new_balance": new_balance
    }
    
    if idempotency_key:
        store_idempotency_key(idempotency_key, result)
    
    try:
        asyncio.create_task(
            manager.broadcast_transaction(account_number, transaction)
        )
    except RuntimeError:
        pass 
    
    return result


def do_withdraw(
    account_number: str,
    amount: float,
    idempotency_key: Optional[str] = None
) -> dict:
    """Withdraw funds from a bank account."""
    # Check idempotency
    if idempotency_key:
        cached = check_idempotency_key(idempotency_key)
        if cached:
            cached["idempotent_replay"] = True
            return cached
    
    # Validate amount
    if amount <= 0:
        return {"success": False, "error": "Amount must be positive"}
    
    account = get_account(account_number)
    if not account:
        return {"success": False, "error": f"Account {account_number} not found"}
    
    if account['balance'] < amount:
        return {
            "success": False,
            "error": f"Insufficient funds. Available balance: ${account['balance']:.2f}"
        }
    
    new_balance = account['balance'] - amount
    update_balance(account['id'], new_balance)
    
    transaction = record_transaction(
        account_id=account['id'],
        transaction_type="WITHDRAWAL",
        amount=amount,
        balance_after=new_balance,
        description=f"Withdrawal of ${amount:.2f}"
    )
    
    result = {
        "success": True,
        "message": f"Successfully withdrew ${amount:.2f}",
        "transaction": transaction,
        "new_balance": new_balance
    }
    
    if idempotency_key:
        store_idempotency_key(idempotency_key, result)
    
    try:
        asyncio.create_task(
            manager.broadcast_transaction(account_number, transaction)
        )
    except RuntimeError:
        pass 
    
    return result


def do_get_balance(account_number: str) -> dict:
    """Get the current balance of a bank account."""
    account = get_account(account_number)
    if not account:
        return {"success": False, "error": f"Account {account_number} not found"}
    
    return {
        "success": True,
        "account_number": account['account_number'],
        "holder_name": account['holder_name'],
        "balance": account['balance'],
        "formatted_balance": f"${account['balance']:.2f}"
    }


def do_get_transaction_history(account_number: str, limit: int = 10) -> dict:
    """Get recent transaction history for a bank account."""
    account = get_account(account_number)
    if not account:
        return {"success": False, "error": f"Account {account_number} not found"}
    
    transactions = get_transactions(account['id'], limit)
    
    return {
        "success": True,
        "account_number": account_number,
        "holder_name": account['holder_name'],
        "current_balance": account['balance'],
        "transaction_count": len(transactions),
        "transactions": transactions
    }


#  MCP Tools (wrapping business logic) 

@mcp.tool
def create_account(holder_name: str) -> dict:
    """
    Create a new bank account for a customer.
    
    Args:
        holder_name: The full name of the account holder
        
    Returns:
        Account details including the generated account number
    """
    return do_create_account(holder_name)


@mcp.tool
def deposit(
    account_number: str,
    amount: float,
    idempotency_key: Optional[str] = None
) -> dict:
    """
    Deposit funds into a bank account.
    
    Args:
        account_number: The 10-digit account number
        amount: The amount to deposit (must be positive)
        idempotency_key: Optional key to prevent duplicate transactions
        
    Returns:
        Transaction details and new balance
    """
    return do_deposit(account_number, amount, idempotency_key)


@mcp.tool
def withdraw(
    account_number: str,
    amount: float,
    idempotency_key: Optional[str] = None
) -> dict:
    """
    Withdraw funds from a bank account.
    
    Args:
        account_number: The 10-digit account number
        amount: The amount to withdraw (must be positive)
        idempotency_key: Optional key to prevent duplicate transactions
        
    Returns:
        Transaction details and new balance
    """
    return do_withdraw(account_number, amount, idempotency_key)


@mcp.tool
def get_balance(account_number: str) -> dict:
    """
    Get the current balance of a bank account.
    
    Args:
        account_number: The 10-digit account number
        
    Returns:
        Current account balance and account holder info
    """
    return do_get_balance(account_number)


@mcp.tool
def get_transaction_history(account_number: str, limit: int = 10) -> dict:
    """
    Get recent transaction history for a bank account.
    
    Args:
        account_number: The 10-digit account number
        limit: Maximum number of transactions to return (default: 10)
        
    Returns:
        List of recent transactions
    """
    return do_get_transaction_history(account_number, limit)


#  Custom REST API Routes 

@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> JSONResponse:
    """Root endpoint with API information."""
    return JSONResponse({
        "name": "MCP Banking Server",
        "version": "1.0.0",
        "description": "A production-ready banking API with MCP integration",
        "default_api_key": get_default_api_key(),
        "endpoints": {
            "accounts": "/accounts",
            "health": "/health",
            "mcp": "/mcp/"
        },
        "features": [
            "MCP tools for LLM integration",
            "REST API endpoints",
            "API key authentication",
            "Idempotency support",
            "WebSocket live updates",
            "CSV export"
        ]
    })


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for monitoring."""
    return JSONResponse({
        "status": "healthy",
        "service": "MCP Banking Server",
        "version": "1.0.0",
        "websocket_connections": manager.get_total_connections()
    })


@mcp.custom_route("/accounts", methods=["POST"])
async def api_create_account(request: Request) -> JSONResponse:
    """Create a new bank account."""
    if not verify_api_key(request):
        return unauthorized_response()
    
    try:
        body = await request.json()
        holder_name = body.get("holder_name", "").strip()
    except:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    
    if not holder_name:
        return JSONResponse({"error": "holder_name is required"}, status_code=400)
    
    result = do_create_account(holder_name)
    if not result.get("success"):
        return JSONResponse({"error": result.get("error")}, status_code=400)
    
    return JSONResponse(result, status_code=201)


@mcp.custom_route("/accounts/{account_number}", methods=["GET"])
async def api_get_account(request: Request) -> JSONResponse:
    """Get account details."""
    if not verify_api_key(request):
        return unauthorized_response()
    
    account_number = request.path_params.get("account_number")
    result = do_get_balance(account_number)
    
    if not result.get("success"):
        return JSONResponse({"error": result.get("error")}, status_code=404)
    
    return JSONResponse(result)


@mcp.custom_route("/accounts/{account_number}/deposit", methods=["POST"])
async def api_deposit(request: Request) -> JSONResponse:
    """Deposit funds into an account."""
    if not verify_api_key(request):
        return unauthorized_response()
    
    account_number = request.path_params.get("account_number")
    idempotency_key = request.headers.get("Idempotency-Key")
    
    try:
        body = await request.json()
        amount = float(body.get("amount", 0))
    except:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    
    result = do_deposit(account_number, amount, idempotency_key)
    
    if not result.get("success"):
        return JSONResponse({"error": result.get("error")}, status_code=400)
    
    return JSONResponse(result)


@mcp.custom_route("/accounts/{account_number}/withdraw", methods=["POST"])
async def api_withdraw(request: Request) -> JSONResponse:
    """Withdraw funds from an account."""
    if not verify_api_key(request):
        return unauthorized_response()
    
    account_number = request.path_params.get("account_number")
    idempotency_key = request.headers.get("Idempotency-Key")
    
    try:
        body = await request.json()
        amount = float(body.get("amount", 0))
    except:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    
    result = do_withdraw(account_number, amount, idempotency_key)
    
    if not result.get("success"):
        status = 422 if "Insufficient" in result.get("error", "") else 400
        return JSONResponse({"error": result.get("error")}, status_code=status)
    
    return JSONResponse(result)


@mcp.custom_route("/accounts/{account_number}/transactions", methods=["GET"])
async def api_get_transactions(request: Request) -> JSONResponse:
    """Get transaction history for an account."""
    if not verify_api_key(request):
        return unauthorized_response()
    
    account_number = request.path_params.get("account_number")
    limit = int(request.query_params.get("limit", 10))
    limit = min(max(limit, 1), 100)  # Clamp between 1 and 100
    
    result = do_get_transaction_history(account_number, limit)
    
    if not result.get("success"):
        return JSONResponse({"error": result.get("error")}, status_code=404)
    
    return JSONResponse(result)


@mcp.custom_route("/accounts/{account_number}/transactions/export", methods=["GET"])
async def api_export_transactions(request: Request) -> StreamingResponse:
    """Export all transactions as CSV file."""
    if not verify_api_key(request):
        return JSONResponse(
            {"error": "Unauthorized", "detail": "Include valid 'X-API-Key' header"},
            status_code=401
        )
    
    account_number = request.path_params.get("account_number")
    account = get_account(account_number)
    
    if not account:
        return JSONResponse(
            {"error": f"Account {account_number} not found"},
            status_code=404
        )
    
    transactions = get_all_transactions(account['id'])
    
    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["ID", "Type", "Amount", "Balance After", "Description", "Date"])
        yield output.getvalue()
        output.seek(0)
        output.truncate()
        
        # Write transactions
        for txn in transactions:
            writer.writerow([
                txn['id'],
                txn['type'],
                f"${txn['amount']:.2f}",
                f"${txn['balance_after']:.2f}",
                txn['description'],
                txn['created_at']
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate()
    
    filename = f"transactions_{account_number}.csv"
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@mcp.custom_route("/ws/transactions/{account_number}", methods=["GET"])
async def websocket_upgrade_info(request: Request) -> JSONResponse:
    """Info about the WebSocket endpoint."""
    return JSONResponse({
        "message": "This is a WebSocket endpoint",
        "usage": "Connect using WebSocket protocol (ws://)",
        "example": "ws://localhost:8000/ws/transactions/{account_number}"
    })


# ============== Run Server ==============

if __name__ == "__main__":
    print("\n Starting MCP Banking Server...")
    print(" Root endpoint: http://localhost:8000/")
    print(" Health check: http://localhost:8000/health")
    print(" MCP endpoint: http://localhost:8000/mcp/")
    
    if DISABLE_AUTH:
        print("\n  WARNING: Authentication is DISABLED (DISABLE_AUTH=true)")
    else:
        print("\n Authentication is ENABLED (use X-API-Key header)")
    
    print()
    mcp.run(transport="http", host="0.0.0.0", port=8000)
