import json
import requests
import os

def lambda_handler(event, context):
    """
    Lambda proxy for AgentCore Gateway following the MCP-compatible format.

    TIMEZONE HANDLING (IMPORTANT):
    - Backend is in America/Guayaquil timezone (GMT-5)
    - Agent sends ISO format dates with UTC timezone (Z suffix)
    - This handler converts UTC dates to GMT-5 local dates before API calls
    - This prevents date shifting (e.g., 2025-12-30 becoming 2025-12-29)
    - Both getAvailableTimes and createBooking apply timezone conversion

    Tools handled:
    - getServices: List all available services
    - getEstablishmentsByServices: Get establishments offering services
    - getAvailableTimes: Get appointment slots (with timezone conversion)
    - createBooking: Create appointment (with timezone conversion)
    """
    print(f"Received event: {json.dumps(event)}")

    delimiter = "___"
    original_tool_name = context.client_context.custom['bedrockAgentCoreToolName']
    tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]

    parameters = event

    API_BASE = "https://tempobook.virtusproject.com/api"
    AUTH_TOKEN = "ToKenBookingAuth123%"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}

    try:
        if tool_name == 'getServices':
            response = requests.get(f"{API_BASE}/services", headers=headers)
            response.raise_for_status()
            result = response.json()

        elif tool_name == 'getEstablishmentsByServices':
            service_ids = parameters.get('service_ids', [])
            service_ids_str = ','.join(service_ids) if isinstance(service_ids, list) else service_ids
            response = requests.get(
                f"{API_BASE}/establishments/establishments-by-services",
                params={"services": service_ids_str},
                headers=headers
            )
            response.raise_for_status()
            result = response.json()

        elif tool_name == 'getAvailableTimes':
            services = parameters.get('services', [])
            if isinstance(services, str):
                services = json.loads(services)

            from datetime import datetime
            import pytz

            # TIMEZONE FIX: Convert ISO date to GMT-5 local date
            # Agent sends ISO format, backend expects YYYY-MM-DD in GMT-5
            iso_date = parameters.get('date')
            if iso_date and 'T' in iso_date:  # It's ISO format
                utc_dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
                gmt5_tz = pytz.timezone('America/Guayaquil')
                local_dt = utc_dt.astimezone(gmt5_tz)
                date_param = local_dt.strftime('%Y-%m-%d')
            else:
                # Already in YYYY-MM-DD format
                date_param = iso_date

            response = requests.get(
                f"{API_BASE}/bookings/availableTime",
                params={
                    "date": date_param,
                    "establishmentId": parameters.get('establishment_id'),
                    "duration": parameters.get('total_duration', 0),
                    "services": json.dumps(services)
                },
                headers=headers
            )
            response.raise_for_status()
            result = response.json()

        elif tool_name == 'createBooking':
            services_selected = parameters.get('services_selected', [])
            if isinstance(services_selected, str):
                services_selected = json.loads(services_selected)

            schedule_selected = parameters.get('schedule_selected', {})
            if isinstance(schedule_selected, str):
                schedule_selected = json.loads(schedule_selected)

            establishment_id = parameters.get('establishment_id')
            establishment_name = parameters.get('establishment_name')
            iso_date = schedule_selected.get('isoDate')

            from datetime import datetime
            import pytz

            # TIMEZONE FIX: Backend is in America/Guayaquil (GMT-5)
            # Parse ISO datetime as UTC, then convert to GMT-5 local time
            utc_dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
            gmt5_tz = pytz.timezone('America/Guayaquil')
            local_dt = utc_dt.astimezone(gmt5_tz)

            # Extract date and time in GMT-5 local timezone
            # This ensures the date matches what user selected, not UTC date
            date_str = local_dt.strftime('%Y-%m-%d')
            time_str = local_dt.strftime('%H:%M')

            duration = int(parameters.get('total_duration', 0))

            available_times_response = requests.get(
                f"{API_BASE}/bookings/availableTime",
                params={
                    "date": date_str,
                    "establishmentId": establishment_id,
                    "duration": duration,
                    "services": json.dumps([s.get('_id', s.get('id')) for s in services_selected])
                },
                headers=headers
            )
            available_times_response.raise_for_status()
            available_times_data = available_times_response.json()

            matching_hour = None
            for slot in available_times_data.get('availableTime', []):
                if slot.get('startTime') == time_str:
                    matching_hour = {
                        "startTime": slot.get('startTime'),
                        "endTime": slot.get('endTime'),
                        "time": slot.get('time'),
                        "duration": slot.get('duration'),
                        "employees": slot.get('employees', [])
                    }
                    break

            if not matching_hour:
                return {'error': f'No available time slot found for {time_str}'}

            schedule_selected = {
                "establishment": {
                    "_id": establishment_id,
                    "name": establishment_name
                },
                "date": date_str,
                "hour": matching_hour
            }

            payload = {
                "customerInfo": {
                    "email": parameters.get('customer_email'),
                    "name": parameters.get('customer_name'),
                    "lastName": parameters.get('customer_last_name'),
                    "phoneNumber": parameters.get('customer_phone'),
                    "phoneCode": parameters.get('customer_phone_code'),
                    "source": {"type": "whatsapp", "detail": "AI Agent"}
                },
                "duration": duration,
                "servicesSelected": services_selected,
                "scheduleSelected": schedule_selected
            }
            response = requests.post(f"{API_BASE}/bookings/", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

        else:
            return {'error': f'Unknown tool: {tool_name}'}

        return result

    except Exception as e:
        print(f"Error executing {tool_name}: {str(e)}")
        return {'error': str(e)}