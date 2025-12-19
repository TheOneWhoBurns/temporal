# AWS Bedrock AgentCore Implementation Guide

Complete reference guide for implementing agents with AWS Bedrock AgentCore and Strands Agents SDK.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Concepts](#core-concepts)
3. [Session Management](#session-management)
4. [Entrypoint Function Patterns](#entrypoint-function-patterns)
5. [Initialization Strategies](#initialization-strategies)
6. [Performance Optimization](#performance-optimization)
7. [Strands Agents Integration](#strands-agents-integration)
8. [AgentCore Gateway Integration](#agentcore-gateway-integration)
9. [WhatsApp Booking Agent Example](#whatsapp-booking-agent-example)
10. [Troubleshooting](#troubleshooting)
11. [References](#references)

---

## Architecture Overview

### What is Bedrock AgentCore?

AWS Bedrock AgentCore is a fully managed service for deploying AI agents at scale. It provides:

- **Managed Infrastructure**: Auto-scaling microVM containers for agent execution
- **Session Isolation**: Dedicated compute resources per conversation session
- **State Management**: Persistent session storage across multiple invocations
- **Security**: Complete isolation between sessions, memory sanitization
- **Scalability**: Automatic scaling to handle thousands of concurrent sessions

### High-Level Flow

```
User Input → AWS API Call → AgentCore Session
    ↓
    Container Spin-up (if new session) → Run Agent Code
    ↓
    Agent processes tools/LLM calls → Returns response
    ↓
    Session remains Active or goes to Idle
    ↓
    User receives response
```

### Container Model

- **One container per session**: Dedicated microVM per conversation
- **Container pinning**: Sessions maintain their containers across multiple invocations
- **Container lifecycle**:
  - Created on first invocation
  - Remains active while processing
  - Goes to Idle state when waiting
  - Terminated after 8 hours or 15 minutes of inactivity
  - Complete memory sanitization on termination

---

## Core Concepts

### BedrockAgentCoreApp

The `BedrockAgentCoreApp` is a minimalist web framework that:

- Wraps your Python function as a web service
- Handles AgentCore Runtime protocol
- No need for Flask/FastAPI boilerplate
- Automatically manages request/response serialization

### Key Components

| Component | Purpose |
|-----------|---------|
| `@app.entrypoint` | Decorator marking the main agent function |
| `payload` | Input dictionary containing user message and context |
| `context` | Optional RequestContext with session info (if using FastAPI) |
| `app.run()` | Starts the local server (port 8080) |

### Initialization Time Constraints

| Phase | Duration | Notes |
|-------|----------|-------|
| Lambda init | ~10 seconds | Module-level imports, global initialization |
| Session init | ~30 seconds | Container spin-up + entrypoint execution |
| Total timeout | 30 seconds | Everything must complete in this window |

---

## Session Management

### Session Lifecycle

1. **Idle** - Waiting for next interaction (0-15 minutes)
2. **Active** - Processing request (HealthyBusy state)
3. **Healthy** - Session healthy and ready
4. **Unhealthy** - Container issues (auto-restart)
5. **Terminated** - Inactivity timeout, max duration, or unhealthy after retries

### Session Characteristics

```
Session ID: UUID (minimum 33 characters recommended)
Duration: Up to 8 hours of total runtime
Inactivity Timeout: 15 minutes
Container: Dedicated microVM per session
Memory: Isolated, sanitized on termination
Reuse: Within same conversation/user
```

### Session State Persistence

Sessions persist across multiple invocations:

```python
# Invocation 1
session_id = "user-123-session"
invoke_agent_runtime(agentRuntimeArn, runtimeSessionId=session_id, payload={...})
# Agent maintains state

# Invocation 2 (same session_id)
invoke_agent_runtime(agentRuntimeArn, runtimeSessionId=session_id, payload={...})
# Agent has access to previous context via conversation manager
```

### Managing Sessions from Client

```python
import boto3
import json
import uuid

agentcore = boto3.client('bedrock-agentcore', region_name='us-east-1')

# Create unique session per conversation
session_id = str(uuid.uuid4())

# First invocation
response = agentcore.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:...",
    runtimeSessionId=session_id,
    payload=json.dumps({
        "prompt": "I want to book a service",
        "phone": "+593995604584"
    }).encode()
)

# Second invocation - same session to maintain context
response = agentcore.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:...",
    runtimeSessionId=session_id,  # Reuse same session
    payload=json.dumps({
        "prompt": "Available on Tuesday?",
        "phone": "+593995604584"
    }).encode()
)
```

### Backend Responsibilities

Your backend application must:

1. **Generate and store session IDs** - Map users to sessions
2. **Reuse session IDs for follow-ups** - Maintain conversation context
3. **Handle session expiry** - Clean up after 15 minutes of inactivity
4. **Rate limiting per session** - Prevent abuse
5. **Session cleanup** - Remove after max duration

---

## Entrypoint Function Patterns

### Pattern 1: Basic Entrypoint (Simple Agents)

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()

# Initialize agent at module level
agent = Agent(
    model="claude-3-5-sonnet-20241022",
    system_prompt="You are a helpful assistant."
)

@app.entrypoint
def invoke(payload):
    """Main agent entrypoint."""
    user_message = payload.get("prompt", "")
    result = agent(user_message)
    return {"response": result.message}

if __name__ == "__main__":
    app.run()
```

**Pros:**
- Simplest implementation
- Fast initialization for module-level agent
- Works for stateless agents
 
**Cons:**
- Limited session context management
- No per-user customization
- Global state shared across sessions

### Pattern 2: Session-Aware Entrypoint (Recommended)

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.session import S3SessionManager
from strands.agent.conversation_manager import SlidingWindowConversationManager

app = BedrockAgentCoreApp()

# Cache managers per phone/user
_session_managers = {}
_agents = {}

TOOLS = [tool1, tool2, tool3]
SYSTEM_PROMPT = """Your system prompt..."""

def get_session_manager(phone):
    """Reuse session manager for user."""
    if phone not in _session_managers:
        _session_managers[phone] = S3SessionManager(
            session_id=f"whatsapp-{phone}",
            bucket="tempobook-sessions"
        )
    return _session_managers[phone]

def get_or_create_agent(phone):
    """Lazy initialization of agent per session."""
    if phone not in _agents:
        session_mgr = get_session_manager(phone)
        _agents[phone] = Agent(
            session_manager=session_mgr,
            conversation_manager=SlidingWindowConversationManager(window_size=20),
            model="deepseek-r1",
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS
        )
    return _agents[phone]

@app.entrypoint
def invoke(payload):
    """Main agent entrypoint with session management."""
    phone = payload.get('phone', 'unknown')
    message = payload.get('prompt', payload.get('message', ''))

    agent = get_or_create_agent(phone)
    response = agent(message)

    return {
        "response": response.message,
        "phone": phone
    }

if __name__ == "__main__":
    app.run()
```

**Pros:**
- Per-user session management
- Conversation context persists
- Caches expensive initialization
- Optimal for multi-user scenarios

**Cons:**
- More complex code
- Memory usage for multiple agents
- Need cleanup strategy

### Pattern 3: FastAPI with Custom Server

```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any, Optional
import uvicorn

app = FastAPI(title="Agent Server", version="1.0.0")

class InvocationRequest(BaseModel):
    prompt: str
    phone: Optional[str] = None

class InvocationResponse(BaseModel):
    response: str

# Initialize agent
agent = None

def initialize_agent():
    global agent
    if agent is None:
        from strands import Agent
        agent = Agent(
            model="deepseek-r1",
            system_prompt="You are helpful.",
            tools=[]
        )
    return agent

@app.post("/invocations", response_model=InvocationResponse)
async def invoke_agent(request: InvocationRequest):
    """Invoke agent with user message."""
    agent = initialize_agent()
    result = agent(request.prompt)
    return InvocationResponse(response=result.message)

@app.get("/ping")
async def ping():
    """Health check endpoint."""
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

**Pros:**
- Full control over API structure
- Can implement streaming
- Better error handling options
- Support for multiple endpoints

**Cons:**
- More boilerplate code
- Need to implement health checks
- Manual initialization

---

## Initialization Strategies

### Strategy 1: Global Initialization (Module-Level)

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()

# Agent initialized at module load time
agent = Agent(
    model="deepseek-r1",
    tools=[tool1, tool2, tool3]
)

@app.entrypoint
def invoke(payload):
    return {"response": agent(payload.get("prompt")).message}
```

**When to use:**
- Simple agents with no per-user state
- Fixed tool set
- Stateless operations

**Trade-offs:**
- ✅ Faster first invocation
- ❌ Longer container startup
- ❌ No session isolation

### Strategy 2: Lazy Initialization (On First Use)

```python
agent = None

def initialize_agent():
    global agent
    if agent is None:
        agent = Agent(
            model="deepseek-r1",
            tools=[tool1, tool2, tool3]
        )
    return agent

@app.entrypoint
def invoke(payload):
    agent = initialize_agent()
    return {"response": agent(payload.get("prompt")).message}
```

**When to use:**
- Complex agent initialization
- Heavy dependencies
- Large model loading
- Optional tool sets

**Trade-offs:**
- ✅ Fast container startup
- ✅ Can initialize on demand
- ❌ First invocation slower
- ❌ Still within 30s window

### Strategy 3: Per-Session Agent Caching

```python
_agents = {}

def get_or_create_agent(session_id):
    if session_id not in _agents:
        _agents[session_id] = Agent(
            session_manager=S3SessionManager(
                session_id=session_id,
                bucket="agent-sessions"
            ),
            conversation_manager=SlidingWindowConversationManager(window_size=20),
            model="deepseek-r1",
            tools=[tool1, tool2, tool3]
        )
    return _agents[session_id]

@app.entrypoint
def invoke(payload):
    session_id = payload.get('session_id', 'default')
    message = payload.get('prompt')

    agent = get_or_create_agent(session_id)
    response = agent(message)

    return {"response": response.message}
```

**When to use:**
- Multi-user applications
- State per conversation
- Long-running sessions
- WhatsApp/Chat agents

**Trade-offs:**
- ✅ Per-session context
- ✅ Conversation persistence
- ✅ Reasonable performance
- ⚠️ Memory per active session

---

## Performance Optimization

### 1. Minimize Container Image Size

```dockerfile
# Use minimal base image
FROM python:3.11-slim

# Install only required packages
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY agent.py .

EXPOSE 8080
CMD ["python", "agent.py"]
```

### 2. Use Lazy Imports for Heavy Dependencies

```python
# DON'T do this at module level
import torch
import transformers

# DO this instead
def load_model():
    import torch
    import transformers
    return transformers.AutoModel.from_pretrained("...")
```

### 3. Implement Proper Health Checks

```python
from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.get("/ping")
def health_check():
    return {"status": "healthy"}

@app.entrypoint
def invoke(payload):
    # Agent logic
    pass
```

### 4. Leverage Session Reuse

```python
# Sessions remain active for 15 minutes
# Multiple invocations within same session = warm container
# Always reuse same session_id for same user/conversation

session_id = "user-123-conv-1"
for message in messages:
    invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,  # Reuse!
        payload=json.dumps({"prompt": message}).encode()
    )
```

### 5. Use ARM64 (AWS Graviton)

```yaml
# In .bedrock_agentcore.yaml
agents:
  my_agent:
    platform: linux/arm64  # Use Graviton
    runtime_type: PYTHON_3_11
```

**Benefits:**
- 20% better price/performance
- AgentCore optimized for ARM64
- Automatic with starter toolkit

### 6. Optimize Tool Loading

```python
# BEFORE: Load all tools
agent = Agent(
    model="deepseek-r1",
    tools=[
        get_services,
        get_establishments,
        get_availability,
        create_booking,
        update_booking,
        cancel_booking,
        send_sms,
        send_email,
        # ... 10 more tools
    ]
)

# AFTER: Load only needed tools
BOOKING_TOOLS = [
    get_services,
    get_establishments,
    get_availability,
    create_booking
]

agent = Agent(
    model="deepseek-r1",
    tools=BOOKING_TOOLS,  # Only tools used
    load_tools_from_directory=False  # Disable auto-load
)
```

### 7. Use Streaming for Real-Time Feedback

```python
@app.entrypoint
def invoke(payload):
    message = payload.get('prompt')

    # Streaming response
    response_text = ""
    for chunk in agent.stream(message):
        response_text += chunk

    return {"response": response_text}
```

---

## Strands Agents Integration

### Basic Integration

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent, tool

app = BedrockAgentCoreApp()

@tool
def get_weather(location: str) -> str:
    """Get current weather for location."""
    # Implementation
    pass

@tool
def set_reminder(text: str, minutes: int) -> str:
    """Set a reminder."""
    # Implementation
    pass

agent = Agent(
    model="deepseek-r1",
    system_prompt="You are a helpful assistant with weather and reminder tools.",
    tools=[get_weather, set_reminder]
)

@app.entrypoint
def invoke(payload):
    result = agent(payload.get("prompt"))
    return {"response": result.message}
```

### Integration with Session Management

```python
from strands import Agent, tool
from strands.session import S3SessionManager
from strands.agent.conversation_manager import SlidingWindowConversationManager

@tool
def get_services() -> str:
    """List all services."""
    pass

TOOLS = [get_services]
SYSTEM_PROMPT = """You are a booking assistant."""

_agents = {}

def get_agent(user_id):
    if user_id not in _agents:
        session_mgr = S3SessionManager(
            session_id=f"user-{user_id}",
            bucket="agent-sessions"
        )

        _agents[user_id] = Agent(
            session_manager=session_mgr,
            conversation_manager=SlidingWindowConversationManager(window_size=20),
            model="deepseek-r1",
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS
        )
    return _agents[user_id]

@app.entrypoint
def invoke(payload):
    user_id = payload.get('user_id')
    message = payload.get('prompt')

    agent = get_agent(user_id)
    response = agent(message)

    return {"response": response.message}
```

### Integration with Memory Hooks

```python
from strands import Agent
from strands.hooks import HookProvider

class MemoryIntegrationHook(HookProvider):
    def on_agent_initialized(self, event):
        # Load conversation history from Bedrock Memory
        conversations = self.memory_client.get_last_k_turns(
            memory_id=self.memory_id,
            actor_id=event.agent.state.get("user_id"),
            k=100
        )
        # Inject into agent context

agent = Agent(
    model="deepseek-r1",
    hooks=[
        MemoryIntegrationHook(memory_id="my-memory-id")
    ],
    tools=[tool1, tool2]
)
```

---

## AgentCore Gateway Integration

### What is AgentCore Gateway?

AgentCore Gateway is a centralized service that exposes tools to agents via the Model Context Protocol (MCP). Instead of defining tools directly in agents, the Gateway manages tools and makes them available through a secure HTTP endpoint.

**Benefits:**
- Decouples tools from agent code
- Centralized tool management and versioning
- Secure authentication via OAuth/Bearer tokens
- Supports multiple agent frameworks (Strands, LangGraph, CrewAI)
- Tool management without agent redeployment

### Gateway Architecture

```
Agent → HTTP Request (MCP Protocol) → Gateway → Lambda/API Target
                                         ↓
                                    Tool Execution
                                    Response → Agent
```

### Lambda Target Handler Structure

When AgentCore Gateway invokes a Lambda function, it passes:
- **event**: Map of inputSchema properties to their values
- **context**: Contains Bedrock-specific metadata via `context.client_context.custom`

**Critical Implementation Details:**

The context object contains:
```python
{
    "bedrockAgentCoreToolName": "${target_name}___${tool_name}",
    "bedrockAgentCoreMessageVersion": "1.0",
    "bedrockAgentCoreAwsRequestId": "string",
    "bedrockAgentCoreMcpMessageId": "string",
    "bedrockAgentCoreGatewayId": "string",
    "bedrockAgentCoreTargetId": "string"
}
```

**Key points:**
1. Tool name must be extracted from **context**, NOT event
2. Tool name has prefix format: `${target_name}___${tool_name}` (triple underscore delimiter)
3. Manually strip prefix using "___" delimiter to get actual tool name
4. Event object contains input parameters as flat key-value map
5. Return plain JSON directly (NOT API Gateway wrapper)
6. No statusCode wrapping needed

**Tool Name Format CRITICAL:**
```python
# Example: If target is "tempobook-gateway-proxy" and tool is "getServices"
original = "tempobook-gateway-proxy___getServices"  # From context
delimiter = "___"
tool_name = original[original.index(delimiter) + len(delimiter):]
# Result: tool_name = "getServices"
```

**Correct Handler Pattern:**

```python
def lambda_handler(event, context):
    delimiter = "___"
    original_tool_name = context.client_context.custom['bedrockAgentCoreToolName']
    tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]

    message_version = context.client_context.custom['bedrockAgentCoreMessageVersion']
    aws_request_id = context.client_context.custom['bedrockAgentCoreAwsRequestId']
    mcp_message_id = context.client_context.custom['bedrockAgentCoreMcpMessageId']
    gateway_id = context.client_context.custom['bedrockAgentCoreGatewayId']
    target_id = context.client_context.custom['bedrockAgentCoreTargetId']

    # Route based on tool_name (NOT prefixed)
    if tool_name == 'getServices':
        return handle_get_services(event)
    elif tool_name == 'createBooking':
        return handle_create_booking(event)
    else:
        return {'error': f'Unknown tool: {tool_name}'}
```

### Gateway Setup and Configuration

**Gateway Details for Your Project:**
- URL: `https://gateway-quick-start-86f4c6-ezgnfmugzg.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp`
- Gateway ID: `gateway-quick-start-86f4c6-ezgnfmugzg`
- Region: `us-east-1`
- ARN: `arn:aws:bedrock-agentcore:us-east-1:111363583174:gateway/gateway-quick-start-86f4c6-ezgnfmugzg`

**Tools Exposed:**
1. getServices
2. getEstablishmentsByServices
3. getAvailableTimes
4. createBooking

### Authentication

Gateway uses OAuth2 client credentials flow:

```python
import requests

def fetch_access_token(client_id, client_secret, token_url):
    response = requests.post(
        token_url,
        data=f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}",
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    return response.json()['access_token']
```

### Lambda Target Implementation Example

For your TempoBook booking agent, implement each tool as a separate handler function:

```python
def lambda_handler(event, context):
    delimiter = "___"
    original_tool_name = context.client_context.custom['bedrockAgentCoreToolName']
    tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]

    API_BASE = "https://tempobook.virtusproject.com/api"
    AUTH_TOKEN = "ToKenBookingAuth123%"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}

    try:
        if tool_name == 'getServices':
            response = requests.get(f"{API_BASE}/services", headers=headers)
            response.raise_for_status()
            return response.json()

        elif tool_name == 'getEstablishmentsByServices':
            service_ids = event.get('service_ids', [])
            service_ids_str = ','.join(service_ids) if isinstance(service_ids, list) else service_ids
            response = requests.get(
                f"{API_BASE}/establishments/establishments-by-services",
                params={"services": service_ids_str},
                headers=headers
            )
            response.raise_for_status()
            return response.json()

        elif tool_name == 'getAvailableTimes':
            services = event.get('services', [])
            services_response = requests.get(f"{API_BASE}/services", headers=headers)
            all_services = services_response.json().get('services', [])
            services_data = [s for s in all_services if s['_id'] in services]

            payload = {
                "date": event.get('date'),
                "establishmentId": event.get('establishment_id'),
                "duration": int(event.get('total_duration', 0)),
                "services": services_data
            }
            response = requests.post(f"{API_BASE}/bookings/availableTime", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

        elif tool_name == 'createBooking':
            services_selected = event.get('services_selected', [])
            schedule_selected = event.get('schedule_selected', {})

            payload = {
                "customerInfo": {
                    "email": event.get('customer_email'),
                    "name": event.get('customer_name'),
                    "lastName": event.get('customer_last_name'),
                    "phoneNumber": event.get('customer_phone'),
                    "phoneCode": event.get('customer_phone_code'),
                    "source": {"type": "whatsapp", "detail": "AI Agent"}
                },
                "duration": int(event.get('total_duration', 0)),
                "servicesSelected": services_selected,
                "scheduleSelected": schedule_selected
            }
            response = requests.post(f"{API_BASE}/bookings/", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

        else:
            return {'error': f'Unknown tool: {tool_name}'}

    except Exception as e:
        return {'error': str(e)}
```

### Example: Using Gateway with Strands Agent

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
import requests
import json
import os

app = BedrockAgentCoreApp()

GATEWAY_URL = "https://gateway-quick-start-86f4c6-ezgnfmugzg.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
CLIENT_ID = os.environ.get('GATEWAY_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GATEWAY_CLIENT_SECRET')
TOKEN_URL = os.environ.get('GATEWAY_TOKEN_URL')

_access_token = None
_tools_cache = None

def get_access_token():
    global _access_token
    if _access_token is None:
        response = requests.post(
            TOKEN_URL,
            data=f"grant_type=client_credentials&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}",
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        _access_token = response.json()['access_token']
    return _access_token

def list_gateway_tools():
    global _tools_cache
    if _tools_cache is None:
        access_token = get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        payload = {
            "jsonrpc": "2.0",
            "id": "list-tools-request",
            "method": "tools/list"
        }
        response = requests.post(GATEWAY_URL, headers=headers, json=payload)
        _tools_cache = response.json()['result']['tools']
    return _tools_cache

def call_gateway_tool(tool_name, tool_input):
    access_token = get_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = {
        "jsonrpc": "2.0",
        "id": f"tool-call-{tool_name}",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": tool_input
        }
    }
    response = requests.post(GATEWAY_URL, headers=headers, json=payload)
    result = response.json()
    if 'result' in result:
        return result['result']['content'][0]['text']
    else:
        return str(result.get('error', 'Unknown error'))

SYSTEM_PROMPT = """Eres un asistente de reservas útil para un establecimiento de belleza/bienestar.

Tu objetivo es ayudar a los clientes a reservar citas a través de WhatsApp. Sigue este flujo:

1. Saluda al cliente y pregunta qué servicio necesita
2. Muestra los servicios disponibles usando get_services
3. Una vez que elijan servicio(s), pregunta por su fecha preferida
4. Obtén los establecimientos que ofrecen esos servicios usando get_establishments_by_services
5. Obtén las horas disponibles usando get_available_times
6. Una vez que elijan una hora, recopila la información del cliente
7. Crea la reserva usando create_booking
8. Confirma los detalles de la reserva

Mantén las respuestas concisas y amigables.
"""

@app.entrypoint
def invoke(payload):
    phone = payload.get('phone', 'unknown')
    message = payload.get('prompt', payload.get('message', ''))

    agent = Agent(
        model="deepseek-r1",
        system_prompt=SYSTEM_PROMPT
    )

    response = agent(message)
    return {
        "response": response.message,
        "phone": phone
    }

if __name__ == "__main__":
    app.run()
```

### Common Implementation Mistakes

**❌ WRONG: Extracting tool name from event**
```python
tool_name = event.get('tool')  # This is None!
parameters = event.get('arguments')  # Wrong structure
```

**✅ CORRECT: Extracting from context**
```python
tool_name = context.client_context.custom['bedrockAgentCoreToolName']
tool_name = tool_name[tool_name.index("___") + 3:]  # Strip prefix
parameters = event  # Event IS the parameters
```

**❌ WRONG: Returning API Gateway format**
```python
return {
    'statusCode': 200,
    'body': json.dumps(result)
}
```

**✅ CORRECT: Return raw JSON**
```python
return result  # Plain dict/JSON
```

**❌ WRONG: Using requests.get for availableTime**
```python
response = requests.get(f"{API_BASE}/bookings/availableTime", params=...)
```

**✅ CORRECT: Use POST with payload**
```python
payload = {"date": ..., "establishmentId": ..., "services": [...]}
response = requests.post(f"{API_BASE}/bookings/availableTime", json=payload)
```

### Gateway vs Direct Tools Comparison

| Aspect | Direct Tools (Strands @tool) | Gateway Lambda Targets |
|--------|-----|---|
| Tool definition | `@tool` decorator in agent | Inline schema in gateway config |
| Tool location | Agent code | Separate Lambda function |
| Agent init time | Slower (tools imported) | Faster (only MCP client) |
| Tool updates | Requires agent redeploy | No agent redeploy needed |
| Authentication | Agent has API keys | Lambda has API keys |
| Scalability | Per-agent tool logic | Centralized Lambda handler |
| Error handling | In agent code | In Lambda function |
| Tool routing | Agent framework handles | Manual routing in handler |

---

## WhatsApp Booking Agent Example

### Full Implementation

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent, tool
from strands.session import S3SessionManager
from strands.agent.conversation_manager import SlidingWindowConversationManager
import requests

app = BedrockAgentCoreApp()

API_BASE = "https://tempobook.virtusproject.com/api"

# ============================================================================
# TOOLS
# ============================================================================

@tool
def get_services() -> str:
    """Obtiene todos los servicios disponibles para reservar."""
    try:
        response = requests.get(f"{API_BASE}/services")
        response.raise_for_status()
        services = response.json()

        result = "Available services:\n\n"
        for service in services:
            result += f"- {service['name']} ({service['duration']} min, ${service['price']})\n"
            result += f"  ID: {service['_id']}\n"
            if service.get('description'):
                result += f"  Description: {service['description']}\n"
            result += f"  Type: {service['type']}\n\n"

        return result
    except Exception as e:
        return f"Error fetching services: {str(e)}"


@tool
def get_establishments_by_services(service_ids: str) -> str:
    """
    Obtiene los establecimientos que ofrecen servicios específicos.

    Args:
        service_ids: IDs de servicios separados por comas (ej: "6944211deb76a386e5d4370f,69442129eb76a386e5d4371f")
    """
    try:
        response = requests.get(
            f"{API_BASE}/establishments/establishments-by-services",
            params={"services": service_ids}
        )
        response.raise_for_status()
        establishments = response.json()

        if not establishments:
            return "No establishments found offering these services."

        result = "Available establishments:\n\n"
        for est in establishments:
            result += f"- {est['name']}\n"
            result += f"  ID: {est['_id']}\n"
            if est.get('employees'):
                result += f"  Staff available: {len(est['employees'])}\n"
            result += "\n"

        return result
    except Exception as e:
        return f"Error fetching establishments: {str(e)}"


@tool
def get_available_times(date: str, establishment_id: str, service_ids: str, total_duration: int) -> str:
    """
    Obtiene las horas disponibles para reservar.

    Args:
        date: Fecha en formato ISO (ej: "2025-12-19T05:00:00.000Z")
        establishment_id: ID del establecimiento
        service_ids: IDs de servicios separados por comas
        total_duration: Duración total en minutos de todos los servicios combinados
    """
    try:
        service_id_list = service_ids.split(',')

        services_response = requests.get(f"{API_BASE}/services")
        services_response.raise_for_status()
        all_services = services_response.json()

        services_data = [s for s in all_services if s['_id'] in service_id_list]

        payload = {
            "date": date,
            "establishmentId": establishment_id,
            "duration": total_duration,
            "services": services_data
        }

        response = requests.post(f"{API_BASE}/bookings/availableTime", json=payload)
        response.raise_for_status()
        data = response.json()

        if not data:
            return "No available time slots found for this date."

        result = f"Available times for {date.split('T')[0]}:\n\n"
        for slot in data:
            if 'hour' in slot:
                result += f"- {slot['hour']['startTime']} - {slot['hour']['endTime']}\n"

        return result
    except Exception as e:
        return f"Error fetching available times: {str(e)}"


@tool
def create_booking(
    customer_name: str,
    customer_last_name: str,
    customer_email: str,
    customer_phone: str,
    customer_phone_code: str,
    service_ids: str,
    establishment_id: str,
    date: str,
    time: str,
    total_duration: int
) -> str:
    """
    Crea una reserva.

    Args:
        customer_name: Nombre del cliente
        customer_last_name: Apellido del cliente
        customer_email: Email del cliente
        customer_phone: Número de teléfono del cliente
        customer_phone_code: Código de país del teléfono (ej: "+593")
        service_ids: IDs de servicios separados por comas
        establishment_id: ID del establecimiento
        date: Fecha en formato ISO (ej: "2025-12-19T05:00:00.000Z")
        time: Hora de la cita (ej: "10:30")
        total_duration: Duración total en minutos
    """
    try:
        service_id_list = service_ids.split(',')

        services_response = requests.get(f"{API_BASE}/services")
        services_response.raise_for_status()
        all_services = services_response.json()

        services_selected = [s for s in all_services if s['_id'] in service_id_list]

        available_times_payload = {
            "date": date,
            "establishmentId": establishment_id,
            "duration": total_duration,
            "services": services_selected
        }

        available_response = requests.post(
            f"{API_BASE}/bookings/availableTime",
            json=available_times_payload
        )
        available_response.raise_for_status()
        available_slots = available_response.json()

        selected_slot = None
        for slot in available_slots:
            if slot.get('hour', {}).get('startTime') == time:
                selected_slot = slot
                break

        if not selected_slot:
            return f"Time slot {time} is no longer available. Please choose another time."

        booking_payload = {
            "customerInfo": {
                "email": customer_email,
                "name": customer_name,
                "lastName": customer_last_name,
                "phoneNumber": customer_phone,
                "gender": "",
                "identification": "",
                "phoneCode": customer_phone_code,
                "source": {
                    "type": "whatsapp",
                    "detail": "AI Agent"
                }
            },
            "duration": total_duration,
            "servicesSelected": services_selected,
            "scheduleSelected": {
                "establishment": selected_slot['establishment'],
                "hour": selected_slot['hour'],
                "date": date
            },
            "employeeSelected": None
        }

        response = requests.post(f"{API_BASE}/bookings/", json=booking_payload)
        response.raise_for_status()
        result = response.json()

        confirmation = f"Booking confirmed!\n\n"
        confirmation += f"Name: {result['booking']['customer']['name']} {result['booking']['customer']['lastName']}\n"
        confirmation += f"Date: {result['booking']['date']}\n"
        confirmation += f"Time: {result['booking']['startTime']} - {result['booking']['endTime']}\n"
        confirmation += f"Location: {result['booking']['establishment']['name']}\n"
        confirmation += f"Services:\n"
        for service in result['booking']['services']:
            confirmation += f"  - {service['name']} ({service['duration']} min)\n"

        return confirmation
    except Exception as e:
        return f"Error creating booking: {str(e)}"


# ============================================================================
# AGENT CONFIGURATION
# ============================================================================

TOOLS = [
    get_services,
    get_establishments_by_services,
    get_available_times,
    create_booking
]

SYSTEM_PROMPT = """Eres un asistente de reservas útil para un establecimiento de belleza/bienestar.

Tu objetivo es ayudar a los clientes a reservar citas a través de WhatsApp. Sigue este flujo:

1. Saluda al cliente y pregunta qué servicio necesita
2. Muestra los servicios disponibles usando get_services()
3. Una vez que elijan servicio(s), pregunta por su fecha preferida
4. Obtén los establecimientos que ofrecen esos servicios usando get_establishments_by_services()
5. Obtén las horas disponibles usando get_available_times()
6. Una vez que elijan una hora, recopila la información del cliente:
   - Nombre completo (nombre y apellido por separado)
   - Email
   - Número de teléfono con código de país
7. Crea la reserva usando create_booking()
8. Confirma los detalles de la reserva

Mantén las respuestas concisas y amigables. Siempre confirma las selecciones antes de proceder.
Calcula la duración total sumando las duraciones de todos los servicios seleccionados.
Usa formato ISO para fechas (ej: "2025-12-19T05:00:00.000Z").
"""

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

_agents = {}

def get_or_create_agent(phone: str):
    """Get or create agent instance for phone number."""
    if phone not in _agents:
        session_mgr = S3SessionManager(
            session_id=f"whatsapp-{phone}",
            bucket="tempobook-sessions"
        )

        _agents[phone] = Agent(
            session_manager=session_mgr,
            conversation_manager=SlidingWindowConversationManager(window_size=20),
            model="deepseek-r1",
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS
        )

    return _agents[phone]

# ============================================================================
# ENTRYPOINT
# ============================================================================

@app.entrypoint
def invoke(payload):
    """Main entrypoint for WhatsApp messages."""

    phone = payload.get('phone', 'unknown')
    message = payload.get('prompt', payload.get('message', ''))

    agent = get_or_create_agent(phone)
    response = agent(message)

    return {
        "response": response.message,
        "phone": phone
    }


if __name__ == "__main__":
    app.run()
```

### Invoking from WhatsApp Webhook

```python
import boto3
import json

agentcore = boto3.client('bedrock-agentcore', region_name='us-east-1')

def handle_whatsapp_message(phone_number, message_text):
    """Handle incoming WhatsApp message."""

    # Use phone number as session ID
    session_id = f"whatsapp-{phone_number}"

    # Invoke agent
    response = agentcore.invoke_agent_runtime(
        agentRuntimeArn="arn:aws:bedrock-agentcore:us-east-1:111363583174:runtime/tempobook-ZZ2WidGgEw",
        runtimeSessionId=session_id,
        payload=json.dumps({
            "phone": phone_number,
            "prompt": message_text
        }).encode()
    )

    # Parse response
    result = json.loads(response['payload'].read().decode())

    # Send back via WhatsApp
    send_whatsapp_message(phone_number, result['response'])
```

---

## Booking API Endpoints (TempoBook)

### Overview

These endpoints are used by the WhatsApp booking agent to interact with the TempoBook backend. They handle the complete booking flow from service selection to appointment confirmation.

**Base URL:** `https://tempobook.virtusproject.com/api`
**Authentication:** Bearer token `ToKenBookingAuth123%`

---

### 1. Get Services

Retrieve all available services in the system.

**Endpoint:**
```
GET /api/services
```

**Authentication:**
```
Authorization: Bearer ToKenBookingAuth123%
```

**Query Parameters:**
None (optional: `search`, `page`, `limit`)

**cURL:**
```bash
curl -X GET "https://tempobook.virtusproject.com/api/services" \
  -H "Authorization: Bearer ToKenBookingAuth123%"
```

**Response (200 OK):**
```json
{
  "status": true,
  "services": [
    {
      "_id": "69442129eb76a386e5d4371f",
      "name": "Bronceado",
      "description": "",
      "gender": "All",
      "type": "Servicios Generales",
      "duration": 10,
      "price": 0,
      "taxRate": 0,
      "createdAt": "2025-12-17T21:18:22.937Z",
      "updatedAt": "2025-12-17T21:18:22.937Z",
      "__v": 0
    },
    {
      "_id": "6944211deb76a386e5d4370f",
      "name": "Depilacion 2",
      "description": "",
      "gender": "All",
      "type": "Servicios Generales",
      "duration": 20,
      "price": 0,
      "taxRate": 0,
      "createdAt": "2025-12-17T21:18:22.937Z",
      "updatedAt": "2025-12-17T21:18:22.937Z",
      "__v": 0
    }
  ]
}
```

**Key Fields:**
- `_id`: Service ID (use in subsequent requests)
- `duration`: Service duration in minutes
- `price`: Service price

---

### 2. Get Establishments by Services

Get establishments offering specific services.

**Endpoint:**
```
GET /api/establishments/establishments-by-services
```

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `services` | string | Yes | Service IDs (comma-separated or single) |

**cURL:**
```bash
curl -X GET "https://tempobook.virtusproject.com/api/establishments/establishments-by-services?services=69442129eb76a386e5d4371f" \
  -H "Authorization: Bearer ToKenBookingAuth123%"
```

**Response (200 OK):**
```json
{
  "status": true,
  "establishments": [
    {
      "_id": "6904e2236a90ec17427acc27",
      "name": "FO",
      "address": "Optional address",
      "city": "Optional city",
      "zipCode": "Optional code",
      "isActive": true,
      "employees": [
        {
          "_id": "6904e2456a90ec17427acca0",
          "name": "FO",
          "schedules": [
            {
              "day": "MONDAY",
              "label": "Lunes",
              "opening": "09:00",
              "closing": "17:00",
              "isClosed": false,
              "_id": "6904e2456a90ec17427acca1"
            }
          ],
          "services": [
            "68714c066651248ada8c6c6c",
            "69442129eb76a386e5d4371f"
          ],
          "isActive": true
        }
      ],
      "whatsappClientId": "main",
      "createdAt": "2025-10-31T15:57:49.828Z",
      "updatedAt": "2025-10-31T15:57:49.828Z",
      "__v": 3
    }
  ]
}
```

**Key Fields:**
- `establishments[0]._id`: **REQUIRED for next steps** - Establishment ID
- `establishments[0].name`: Establishment name to display
- `establishments[0].whatsappClientId`: Used for sending notifications

---

### 3. Get Available Times

Get available appointment times.

**Endpoint:**
```
GET /api/bookings/availableTime
```

**Query Parameters:**
| Parameter | Type | Required | Format | Description |
|-----------|------|----------|--------|-------------|
| `date` | string | Yes | `YYYY-MM-DD` | Appointment date |
| `establishmentId` | string | Yes | ObjectId | Establishment ID from step 2 |
| `duration` | number | Yes | minutes | Service total duration |
| `services` | string | Yes | JSON array | Service IDs as JSON: `["id1","id2"]` |

**cURL:**
```bash
curl -X GET "https://tempobook.virtusproject.com/api/bookings/availableTime?date=2025-12-22&establishmentId=6904e2236a90ec17427acc27&duration=10&services=%5B%2269442129eb76a386e5d4371f%22%5D" \
  -H "Authorization: Bearer ToKenBookingAuth123%"
```

**Response (200 OK) - Truncated:**
```json
{
  "message": "Éxito",
  "availableTime": [
    {
      "employees": ["6904e2456a90ec17427acca0"],
      "duration": 10,
      "time": "11:00",
      "startTime": "11:00",
      "endTime": "11:10"
    },
    {
      "employees": ["6904e2456a90ec17427acca0"],
      "duration": 10,
      "time": "11:10",
      "startTime": "11:10",
      "endTime": "11:20"
    }
  ],
  "availableEmployees": [
    {
      "_id": "6904e2456a90ec17427acca0",
      "name": "FO",
      "establishment": "6904e2236a90ec17427acc27",
      "schedules": [...]
    }
  ]
}
```

**Key Fields:**
- `availableTime[].startTime`: **REQUIRED for booking** - Appointment start time
- `availableTime[].endTime`: **REQUIRED for booking** - Appointment end time
- `availableTime[].employees`: Available employee IDs for this slot
- `availableEmployees`: Full employee details with schedules

---

### 4. Create Booking

**Endpoint:**
```
POST /api/bookings/
```

**Request Body:**
```json
{
  "customerInfo": {
    "email": "customer@email.com",
    "name": "Andres",
    "lastName": "Martinez",
    "phoneNumber": "0986928168",
    "phoneCode": "+593",
    "source": {
      "type": "whatsapp",
      "detail": "AI Agent"
    }
  },
  "duration": 10,
  "servicesSelected": [
    {
      "_id": "69442129eb76a386e5d4371f",
      "name": "Bronceado",
      "duration": 10,
      "price": 0
    }
  ],
  "scheduleSelected": {
    "establishment": {
      "_id": "6904e2236a90ec17427acc27",
      "name": "FO"
    },
    "date": "2025-12-22",
    "hour": {
      "startTime": "11:00",
      "endTime": "11:10",
      "time": "11:00",
      "duration": 10,
      "employees": ["6904e2456a90ec17427acca0"]
    }
  }
}
```

**cURL:**
```bash
curl -X POST "https://tempobook.virtusproject.com/api/bookings/" \
  -H "Authorization: Bearer ToKenBookingAuth123%" \
  -H "Content-Type: application/json" \
  -d '{
    "customerInfo": {
      "email": "andres@email.com",
      "name": "Andres",
      "lastName": "Martinez",
      "phoneNumber": "0986928168",
      "phoneCode": "+593",
      "source": {
        "type": "whatsapp",
        "detail": "AI Agent"
      }
    },
    "duration": 10,
    "servicesSelected": [
      {
        "_id": "69442129eb76a386e5d4371f",
        "name": "Bronceado",
        "duration": 10,
        "price": 0
      }
    ],
    "scheduleSelected": {
      "establishment": {
        "_id": "6904e2236a90ec17427acc27",
        "name": "FO"
      },
      "date": "2025-12-22",
      "hour": {
        "startTime": "11:00",
        "endTime": "11:10",
        "time": "11:00",
        "duration": 10,
        "employees": ["6904e2456a90ec17427acca0"]
      }
    }
  }'
```

**Response (201 Created):**
```json
{
  "message": "Cita creada con éxito",
  "booking": {
    "_id": "67666abd6a90ec17427acda0",
    "establishment": {
      "_id": "6904e2236a90ec17427acc27",
      "name": "FO"
    },
    "employee": "6904e2456a90ec17427acca0",
    "date": "2025-12-22",
    "hour": "11:00",
    "startTime": "11:00",
    "endTime": "11:10",
    "customer": {
      "name": "Andres",
      "lastName": "Martinez",
      "email": "andres@email.com",
      "phoneNumber": "0986928168",
      "phoneCode": "+593"
    },
    "services": [
      {
        "_id": "69442129eb76a386e5d4371f",
        "name": "Bronceado",
        "duration": 10,
        "price": 0
      }
    ],
    "duration": 10,
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "state": "Reservado",
    "createdAt": "2025-12-19T14:30:00.000Z",
    "updatedAt": "2025-12-19T14:30:00.000Z"
  }
}
```

**Required Fields:**
- `customerInfo.email`: Customer email
- `customerInfo.name`: Customer first name
- `customerInfo.lastName`: Customer last name
- `customerInfo.phoneNumber`: Phone without country code
- `customerInfo.phoneCode`: Country code (e.g., "+593")
- `duration`: Total service duration in minutes
- `servicesSelected`: Array of selected services with IDs
- `scheduleSelected.establishment._id`: Establishment ID
- `scheduleSelected.date`: Date as `YYYY-MM-DD`
- `scheduleSelected.hour.startTime`: Start time as `HH:MM`
- `scheduleSelected.hour.endTime`: End time as `HH:MM`
- `scheduleSelected.hour.employees`: Array of available employee IDs

**Error Responses:**
- `400 Bad Request`: Missing required fields
- `500 Internal Server Error`: Database errors, invalid data, employee unavailable

---

### Data Flow Summary

**Step 1:** User requests service → Call Get Services
**Step 2:** User selects service → Call Get Establishments by Services
**Step 3:** User picks establishment → Extract establishment ID
**Step 4:** User specifies date → Call Get Available Times
**Step 5:** User selects time → Extract time slot details
**Step 6:** User provides contact info → Call Create Booking
**Step 7:** System confirms → Send confirmation message

---

### Test Data (Available in API)

**Services:**
- Bronceado (10 min, Free): `69442129eb76a386e5d4371f`
- Depilacion 2 (20 min, Free): `6944211deb76a386e5d4370f`
- Servicio general (7 min, $10): `68714c066651248ada8c6c6c`

**Establishments:**
- FO: `6904e2236a90ec17427acc27`
- Shopping: `68714c066651248ada8c6c6e`

**Employees:**
- FO Employee: `6904e2456a90ec17427acca0`
- Juan Pérez: `68714c066651248ada8c6c70`

---

### Create Booking - Live Test Results

**Test Date:** 2025-12-19

**Request Parameters:**
```bash
curl -X POST "https://tempobook.virtusproject.com/api/bookings/" \
  -H "Authorization: Bearer ToKenBookingAuth123%" \
  -H "Content-Type: application/json" \
  -d '{
    "customerInfo": {
      "email": "carlos.test@example.com",
      "name": "Carlos",
      "lastName": "TestUser",
      "phoneNumber": "0991234567",
      "phoneCode": "+593",
      "source": {
        "type": "whatsapp",
        "detail": "AI Agent"
      }
    },
    "duration": 10,
    "servicesSelected": [
      {
        "_id": "69442129eb76a386e5d4371f",
        "name": "Bronceado",
        "duration": 10,
        "price": 0
      }
    ],
    "scheduleSelected": {
      "establishment": {
        "_id": "6904e2236a90ec17427acc27",
        "name": "FO"
      },
      "date": "2025-12-30",
      "hour": {
        "startTime": "09:00",
        "endTime": "09:10",
        "time": "09:00",
        "duration": 10,
        "employees": ["6904e2456a90ec17427acca0"]
      }
    }
  }'
```

**Response (201 Created):**
```json
{
  "message": "Cita creada con éxito",
  "booking": {
    "_id": "6945bdcaac1442bdd6331535",
    "establishment": {
      "_id": "6904e2236a90ec17427acc27",
      "name": "FO"
    },
    "employee": "6904e2456a90ec17427acca0",
    "date": "2025-12-29",
    "hour": "09:00",
    "startTime": "09:00",
    "endTime": "09:10",
    "customer": {
      "phoneNumber": "0991234567",
      "phoneCode": "+593",
      "lastName": "Testuser",
      "email": "carlos.test@example.com",
      "name": "Carlos",
      "gender": "All"
    },
    "services": [
      {
        "_id": "69442129eb76a386e5d4371f",
        "name": "Bronceado",
        "gender": "All",
        "duration": 10,
        "price": 0,
        "taxRate": 0
      }
    ],
    "duration": 10,
    "state": "Reservado",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRlIjoiMjAyNS0xMi0yOSIsImhvdXIiOiIyMDI1LTEyLTE5VDA5OjAwOjAwLjAwMFoiLCJpYXQiOjE3NjYxNzgyNTAsImV4cCI6MTc2Njc4MzA1MH0.vHA-nmy2vbUmL2IpMeCD1Ivjp4f80XCRvNScjZYpYk0",
    "customerId": "6945bda9ac1442bdd63314e9",
    "origin": "whatsapp:AI Agent",
    "kommoLeadId": null,
    "createdBy": {
      "userId": null,
      "name": "cliente",
      "email": null
    },
    "updatedBy": {
      "userId": null,
      "name": "cliente",
      "email": null
    },
    "stamps": [],
    "lineItems": [],
    "logs": [],
    "createdAt": "2025-12-19T21:04:10.613Z",
    "updatedAt": "2025-12-19T21:04:10.613Z",
    "__v": 0
  }
}
```

**Key Points from Response:**
- ✅ Booking created successfully with ID: `6945bdcaac1442bdd6331535`
- ✅ State: `Reservado` (Booked)
- ✅ JWT token generated for customer verification
- ✅ Customer ID auto-generated: `6945bda9ac1442bdd63314e9`
- ✅ All service details preserved
- ✅ Timestamps recorded for audit trail
- ✅ Source tracked as `whatsapp:AI Agent`

---

## Troubleshooting

### Issue: "Runtime initialization time exceeded"

**Causes:**
1. Agent initialization taking >30 seconds
2. Importing heavy dependencies at module level
3. S3 bucket not accessible
4. Network timeouts during initialization

**Solutions:**
```python
# Use lazy initialization
agent = None

@app.entrypoint
def invoke(payload):
    global agent
    if agent is None:
        agent = Agent(...)  # Initialize on first call
    return {"response": agent(payload.get("prompt")).message}

# Use lazy imports
def get_heavy_dependency():
    import torch  # Import only when needed
    return torch

# Add health check
@app.get("/ping")
def health_check():
    return {"status": "healthy"}
```

### Issue: "502 Error from runtime"

**Causes:**
1. Unhandled exception in entrypoint
2. Agent crashes during execution
3. Tool execution fails
4. Invalid payload format

**Solutions:**
```python
@app.entrypoint
def invoke(payload):
    try:
        phone = payload.get('phone', 'unknown')
        message = payload.get('prompt', '')

        if not message:
            return {"error": "No message provided"}

        agent = get_or_create_agent(phone)
        response = agent(message)

        return {
            "response": response.message,
            "phone": phone
        }
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
```

### Issue: "Session not found"

**Causes:**
1. Using different session IDs for same conversation
2. Session timed out (15 minutes of inactivity)
3. Session exceeded 8-hour limit

**Solutions:**
```python
# Always reuse session ID for same user
def get_session_id(user_id):
    return f"user-{user_id}"  # Consistent

# Handle expired sessions gracefully
def invoke_with_retry(agent_arn, session_id, payload):
    try:
        return agentcore.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=session_id,
            payload=payload
        )
    except Exception as e:
        if "not found" in str(e):
            # Create new session
            return agentcore.invoke_agent_runtime(
                agentRuntimeArn=agent_arn,
                runtimeSessionId=str(uuid.uuid4()),
                payload=payload
            )
        raise
```

### Issue: "Memory exceeded"

**Causes:**
1. Too many agents cached in memory
2. Conversation history growing unbounded
3. Large files in session

**Solutions:**
```python
# Implement agent cleanup
MAX_AGENTS = 100
_agents = {}

def get_or_create_agent(phone):
    if len(_agents) > MAX_AGENTS:
        # Remove least recently used
        oldest = min(_agents.items(), key=lambda x: x[1]['last_used'])
        del _agents[oldest[0]]

    if phone not in _agents:
        _agents[phone] = {
            'agent': Agent(...),
            'last_used': time.time()
        }

    _agents[phone]['last_used'] = time.time()
    return _agents[phone]['agent']

# Use smaller conversation window
conversation_mgr = SlidingWindowConversationManager(window_size=10)
```

---

## References

### Official AWS Documentation
- [AWS Bedrock AgentCore Get Started](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-get-started-toolkit.html)
- [Runtime How It Works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
- [Session Management](https://aws.github.io/bedrock-agentcore-starter-toolkit/examples/session-management.html)
- [Use Isolated Sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)

### AWS Samples & Tutorials
- [amazon-bedrock-agentcore-samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
- [bedrock-agentcore-sdk-python](https://github.com/aws/bedrock-agentcore-sdk-python)
- [sample-bedrock-agentcore-with-strands-and-nova](https://github.com/aws-samples/sample-bedrock-agentcore-with-strands-and-nova)

### Strands Agents Documentation
- [Deploying to Bedrock AgentCore](https://strandsagents.com/latest/documentation/docs/user-guide/deploy/deploy_to_bedrock_agentcore/)
- [Production Deployment Best Practices](https://strandsagents.com/latest/documentation/docs/user-guide/deploy/operating-agents-in-production/)
- [Session Management](https://strandsagents.com/latest/documentation/docs/api-reference/session/)

### Blog Posts & Articles
- [AWS Blog: Securely Launch and Scale Agents](https://aws.amazon.com/blogs/machine-learning/securely-launch-and-scale-your-agents-and-tools-on-amazon-bedrock-agentcore-runtime/)
- [AWS Plain English: Getting Started](https://aws.plainenglish.io/getting-started-with-bedrock-agentcore-runtime-3eaae1f517cc)
- [Dev.to: Building Production-Ready AI Agents](https://dev.to/aws/building-production-ready-ai-agents-with-strands-agents-and-amazon-bedrock-agentcore-3dg0)
- [Medium: Bedrock AgentCore Beginner's Guide](https://medium.com/@aitha.jayanth23/getting-started-with-aws-bedrock-agentcore-a-beginners-guide-33319f17b96e)

---

## Quick Reference: Key Timeouts & Limits

| Parameter | Value | Notes |
|-----------|-------|-------|
| Session max duration | 8 hours | Per session total runtime |
| Inactivity timeout | 15 minutes | Before session terminates |
| Initialization window | 30 seconds | Container + entrypoint init |
| Lambda init phase | 10 seconds | Module-level imports |
| Container port | 8080 | Required |
| Container architecture | ARM64 | AWS Graviton (required) |
| Memory per session | Varies | Isolated microVM |
| Session ID length | 33+ chars | UUID recommended |

---

## Quick Reference: Best Practices Checklist

- [ ] Use per-session caching for multi-user agents
- [ ] Implement lazy initialization for heavy dependencies
- [ ] Add health check endpoint (`/ping`)
- [ ] Use sliding window conversation manager for long chats
- [ ] Reuse session IDs for same conversation
- [ ] Handle session expiry gracefully
- [ ] Minimize container image size
- [ ] Use ARM64 (Graviton) architecture
- [ ] Load only needed tools (explicit list)
- [ ] Implement proper error handling in entrypoint
- [ ] Use S3 for session persistence in production
- [ ] Monitor session memory usage
- [ ] Test with `agentcore invoke` locally
- [ ] Test with `agentcore dev` for local debugging
- [ ] Deploy with `agentcore deploy` to AWS

