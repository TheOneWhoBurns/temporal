import json
import requests

def lambda_handler(event, context):
    """
    Lambda proxy for AgentCore Gateway.
    Forwards requests to TempoBook API (or AWS API Gateway once configured).
    """

    print(f"Received event: {json.dumps(event)}")

    # Extract the tool call details from Gateway
    tool_name = event.get('toolName')
    parameters = event.get('parameters', {})

    # TempoBook API base URL (replace with API Gateway URL later)
    API_BASE = "https://tempobook.virtusproject.com/api"

    try:
        if tool_name == 'getServices':
            response = requests.get(f"{API_BASE}/services")
            response.raise_for_status()
            result = response.json()

        elif tool_name == 'getEstablishmentsByServices':
            service_ids = parameters.get('service_ids')
            response = requests.get(
                f"{API_BASE}/establishments/establishments-by-services",
                params={"services": service_ids}
            )
            response.raise_for_status()
            result = response.json()

        elif tool_name == 'getAvailableTimes':
            payload = {
                "date": parameters.get('date'),
                "establishmentId": parameters.get('establishment_id'),
                "duration": int(parameters.get('total_duration')),
                "services": json.loads(parameters.get('services', '[]'))
            }
            response = requests.post(f"{API_BASE}/bookings/availableTime", json=payload)
            response.raise_for_status()
            result = response.json()

        elif tool_name == 'createBooking':
            payload = {
                "customerInfo": {
                    "email": parameters.get('customer_email'),
                    "name": parameters.get('customer_name'),
                    "lastName": parameters.get('customer_last_name'),
                    "phoneNumber": parameters.get('customer_phone'),
                    "phoneCode": parameters.get('customer_phone_code'),
                    "gender": "",
                    "identification": "",
                    "source": {
                        "type": "whatsapp",
                        "detail": "AI Agent"
                    }
                },
                "duration": int(parameters.get('total_duration')),
                "servicesSelected": json.loads(parameters.get('services_selected', '[]')),
                "scheduleSelected": json.loads(parameters.get('schedule_selected', '{}')),
                "employeeSelected": None
            }
            response = requests.post(f"{API_BASE}/bookings/", json=payload)
            response.raise_for_status()
            result = response.json()

        else:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Unknown tool: {tool_name}'})
            }

        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
