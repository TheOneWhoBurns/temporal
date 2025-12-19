# WhatsApp Booking Agent

AI-powered booking agent for WhatsApp built with AWS Bedrock AgentCore and Strands Agents.

## Architecture

- **Model**: DeepSeek R1 (via AWS Bedrock)
- **Framework**: Strands Agents
- **Platform**: AWS Bedrock AgentCore
- **Session Management**: S3SessionManager (persists conversations per phone number)
- **API Integration**: AgentCore Gateway (wraps TempoBook API as MCP tools)
- **API**: TempoBook booking API

## Booking Flow

1. User requests service via WhatsApp
2. Agent shows available services
3. User selects service(s)
4. Agent shows establishments and available dates
5. Agent displays time slots
6. User chooses time
7. Agent collects customer info (name, email, phone)
8. Agent creates booking and sends confirmation

## Gateway Setup

AgentCore Gateway automatically wraps the TempoBook API as MCP tools for the agent.

### Create Gateway

```bash
uv sync
uv run python create_gateway.py
```

This will:
1. Create IAM role for Gateway
2. Create AgentCore Gateway with MCP protocol
3. Add TempoBook API as a target using the OpenAPI spec
4. Output the Gateway MCP endpoint URL

Save the Gateway MCP URL for the next step.

## Setup

### Prerequisites

```bash
uv sync
aws configure
```

### Configuration

1. Create S3 bucket for sessions:
```bash
aws s3 mb s3://tempobook-sessions
```

2. Set Gateway MCP URL as environment variable:
```bash
export GATEWAY_MCP_URL="<your-gateway-mcp-url>"
```

3. Configure AgentCore (use agent_with_gateway.py for Gateway integration):
```bash
uv run agentcore configure -e agent_with_gateway.py
```

4. Deploy:
```bash
uv run agentcore deploy
```

Note: If you prefer using direct API calls without Gateway, use `agent.py` instead of `agent_with_gateway.py`.

## WhatsApp Integration

Invoke from your WhatsApp webhook:

```python
import boto3
import json

client = boto3.client('bedrock-agentcore')

response = client.invoke_agent_runtime(
    agentRuntimeArn="<your-agent-arn>",
    runtimeSessionId=f"whatsapp-{phone_number}",
    payload=json.dumps({
        "phone": phone_number,
        "message": user_message
    }).encode()
)

reply = json.loads(response['payload'].read())['response']
```

## Tools

AgentCore Gateway automatically exposes these tools via MCP from the TempoBook API:

**getServices**
- Lists all available services with duration and pricing
- Mapped from: GET /api/services

**getEstablishmentsByServices**
- Finds establishments offering selected services
- Args: comma-separated service IDs
- Mapped from: GET /api/establishments/establishments-by-services

**getAvailableTimes**
- Shows available time slots for specific date
- Args: date (ISO), establishment ID, service IDs, total duration (minutes)
- Mapped from: POST /api/bookings/availableTime

**createBooking**
- Creates the booking
- Args: customer info, service IDs, establishment, date, time, duration
- Mapped from: POST /api/bookings/

The OpenAPI specification is in `tempobook-api-spec.yaml`.

## Environment Variables

Set in AgentCore configuration:
- `GATEWAY_MCP_URL`: MCP endpoint URL from Gateway setup
- S3 bucket name: `tempobook-sessions` (hardcoded in agent code)

## Testing Locally

```bash
uv run agentcore dev
```

Or test directly:
```bash
uv run agentcore invoke '{"phone": "+593995604584", "message": "I want to book a service"}'
```

## API Endpoints Used

- `GET /api/services`
- `GET /api/establishments/establishments-by-services`
- `POST /api/bookings/availableTime`
- `POST /api/bookings/`

## Session Management

Each WhatsApp conversation is isolated by phone number:
- Session ID: `whatsapp-{phone_number}`
- Storage: S3 (auto-persisted by S3SessionManager)
- Conversation window: 20 messages (SlidingWindowConversationManager)

## Notes

- DeepSeek R1 is cost-effective for this use case
- Sessions persist across message invocations
- Agent maintains conversation context automatically
- All dates use ISO 8601 format
- Phone codes default to international format (e.g., "+593")
