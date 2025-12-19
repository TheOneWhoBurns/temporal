#!/usr/bin/env python3
import boto3
import json
import uuid

agent_arn = "arn:aws:bedrock-agentcore:us-east-1:111363583174:runtime/agent-lTjba1EiAF"
session_id = str(uuid.uuid4())
client = boto3.client('bedrock-agentcore', region_name='us-east-1')
conversation_history = []

def invoke_agent(message):
    """Send a message to the agent and get response"""
    global conversation_history

    history_text = ""
    if conversation_history:
        history_text = "Historial de conversación:\n"
        for msg in conversation_history:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            history_text += f"{role}: {content}\n"
        history_text += "\nMensaje actual:\n"

    full_prompt = history_text + message

    payload = json.dumps({"prompt": full_prompt}).encode()

    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=payload
    )

    conversation_history.append({"role": "user", "content": message})

    try:
        body = response['response'].read().decode('utf-8')
        result = json.loads(body)

        if isinstance(result, dict):
            if 'response' in result:
                agent_response = result['response']
            elif 'message' in result:
                agent_response = result['message']
            elif 'content' in result:
                agent_response = result['content']
            else:
                agent_response = str(result)
        else:
            agent_response = str(result)

        agent_text = str(agent_response)
        conversation_history.append({"role": "assistant", "content": agent_text})

        return agent_response
    except Exception as e:
        return f"Error parsing response: {e}"

def main():
    print("\n━━━ Agent Conversation ━━━")
    print("Type 'exit' to quit\n")

    while True:
        try:
            user_input = input("you: ").strip()
            if not user_input:
                continue
            if user_input.lower() == 'exit':
                print("━━━\n")
                break

            print("agent: ", end="", flush=True)
            response = invoke_agent(user_input)
            print(response)
            print()
        except KeyboardInterrupt:
            print("\n━━━\n")
            break
        except Exception as e:
            print(f"error: {e}\n")

if __name__ == "__main__":
    main()
