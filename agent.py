from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent, tool
from strands.session.s3_session_manager import S3SessionManager
from strands.conversation.sliding_window_conversation_manager import SlidingWindowConversationManager
import requests
import json
from datetime import datetime
from typing import List, Dict, Any

app = BedrockAgentCoreApp()

API_BASE = "https://tempobook.virtusproject.com/api"

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

@app.entrypoint
def invoke(payload):
    """Main entrypoint for WhatsApp messages."""

    phone = payload.get('phone', 'unknown')
    message = payload.get('message', '')

    session_mgr = S3SessionManager(
        session_id=f"whatsapp-{phone}",
        bucket="tempobook-sessions"
    )

    conversation_mgr = SlidingWindowConversationManager(window_size=20)

    agent = Agent(
        session_manager=session_mgr,
        conversation_manager=conversation_mgr,
        model="deepseek-r1",
        system_prompt=SYSTEM_PROMPT,
        tools=[
            get_services,
            get_establishments_by_services,
            get_available_times,
            create_booking
        ]
    )

    response = agent(message)

    return {
        "response": response.message,
        "phone": phone
    }
