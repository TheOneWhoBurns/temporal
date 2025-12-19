import os
import json
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

app = BedrockAgentCoreApp()

GATEWAY_URL = "https://gateway-quick-start-85d706-uza6s7ioim.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
REGION = "us-east-1"

CLIENT_INFO = {
    "client_id": "4bcrnk1v7khmfq0h99fssv6qga",
    "client_secret": "mfaln1f3j5qlc8ndk2q7cqfioamui88e3ut57mhismlc3mh9d0",
    "token_endpoint": "https://my-domain-hqtxbmri.auth.us-east-1.amazoncognito.com/oauth2/token",
    "scope": "gateway-quick-start-85d706/genesis-gateway:invoke"
}

def create_transport(mcp_url, access_token):
    return streamablehttp_client(mcp_url, headers={"Authorization": f"Bearer {access_token}"})


SYSTEM_PROMPT = """
Eres un asistente de reservas útil para un establecimiento de belleza/bienestar.
No te inventes nada, usa solo la información proporcionada por las herramientas.

Tu objetivo es ayudar a los clientes a reservar citas a través de WhatsApp. Sigue este flujo:

1. Saluda al cliente y pregunta qué servicio necesita
2. Muestra los servicios disponibles usando la herramienta 'getServices'
3. Obtén los establecimientos que ofrecen esos servicios usando 'getEstablishmentsByServices'
4. Pide al cliente que elija un establecimiento y una fecha para la cita
5. Obtén las horas disponibles para la fecha y establecimiento elegido usando 'getAvailableTimes'
6. Una vez que elijan una hora, recopila la información del cliente:
   - Nombre completo (nombre y apellido por separado)
   - Email
   - Número de teléfono con código de país
7. Crea la reserva usando 'createBooking' con todos los detalles recopilados
8. Confirma los detalles de la reserva

Mantén las respuestas concisas y amigables. Siempre confirma las selecciones antes de proceder.
Calcula la duración total sumando las duraciones de todos los servicios seleccionados.
Usa formato ISO para fechas (ej: "2025-12-19T05:00:00.000Z").

"""

@app.entrypoint
def invoke(payload, context):
    user_message = payload.get('prompt', payload.get('message', ''))
    session_id = getattr(context, 'session_id', 'default-session')

    client = GatewayClient(region_name=REGION)
    access_token = client.get_access_token_for_cognito(CLIENT_INFO)

    model = BedrockModel(
        model_id="moonshot.kimi-k2-thinking",
        streaming=False
    )

    mcp_client = MCPClient(lambda: create_transport(GATEWAY_URL, access_token))

    with mcp_client:
        tools = mcp_client.list_tools_sync()

        agent = Agent(
            model=model,
            tools=tools,
            system_prompt=SYSTEM_PROMPT
        )

        response = agent(user_message)

    return {
        "response": response.message.get('content', response) if hasattr(response, 'message') else str(response),
        "session_id": session_id
    }

if __name__ == "__main__":
    app.run()