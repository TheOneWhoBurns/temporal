from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
import requests
import os

app = BedrockAgentCoreApp()

GATEWAY_URL = "https://gateway-quick-start-86f4c6-ezgnfmugzg.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
CLIENT_ID = os.environ.get('GATEWAY_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GATEWAY_CLIENT_SECRET')
TOKEN_URL = os.environ.get('GATEWAY_TOKEN_URL')

_access_token = None

def get_access_token():
    global _access_token
    if _access_token is None:
        if not all([CLIENT_ID, CLIENT_SECRET, TOKEN_URL]):
            raise ValueError("Missing gateway credentials: GATEWAY_CLIENT_ID, GATEWAY_CLIENT_SECRET, GATEWAY_TOKEN_URL")
        response = requests.post(
            TOKEN_URL,
            data=f"grant_type=client_credentials&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}",
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        _access_token = response.json()['access_token']

    return _access_token

def call_gateway_tool(tool_name, tool_input):
    try:
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
            return f"Error: {result.get('error', {}).get('message', 'Unknown error')}"
    except Exception as e:
        return f"Error calling gateway tool {tool_name}: {str(e)}"

SYSTEM_PROMPT = 


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
