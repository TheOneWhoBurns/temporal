# Booking System API - Endpoint Documentation

## Overview
This document outlines all API endpoints used by the WhatsApp booking agent, their parameters, and expected responses.

---

## 1. Get Services

Retrieve all available services in the system.

### Endpoint
```
GET /api/services
```

### Authentication
```
Authorization: Bearer ToKenBookingAuth123%
```

### Query Parameters
None (optional: `search`, `page`, `limit`)

### cURL Example
```bash
curl -X GET "https://tempobook.virtusproject.com/api/services" \
  -H "Authorization: Bearer ToKenBookingAuth123%"
```

### Response (200 OK)
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
    }
  ]
}
```

### Key Fields
| Field | Type | Description |
|-------|------|-------------|
| `_id` | string | Service ID (use for subsequent requests) |
| `name` | string | Service name to display to user |
| `duration` | number | Service duration in minutes |
| `price` | number | Service price |

---

## 2. Get Establishments by Services

Get all establishments that offer specific services.

### Endpoint
```
GET /api/establishments/establishments-by-services
```

### Authentication
```
Authorization: Bearer ToKenBookingAuth123%
```

### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `services` | string (comma-separated IDs) | Yes | Service IDs (e.g., `69442129eb76a386e5d4371f` or `id1,id2,id3`) |

### cURL Example
```bash
curl -X GET "https://tempobook.virtusproject.com/api/establishments/establishments-by-services?services=69442129eb76a386e5d4371f" \
  -H "Authorization: Bearer ToKenBookingAuth123%"
```

### Response (200 OK)
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
              "isClosed": false
            }
          ],
          "services": ["68714c066651248ada8c6c6c", "69442129eb76a386e5d4371f"],
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

### Key Fields
| Field | Type | Description |
|-------|------|-------------|
| `_id` | string | **Establishment ID (REQUIRED for next steps)** |
| `name` | string | Establishment name to display to user |
| `address` | string | Establishment address |
| `employees` | array | List of employees at this establishment |
| `employees[].name` | string | Employee name |
| `employees[].schedules` | array | Employee work schedules |
| `whatsappClientId` | string | WhatsApp client ID for notifications |

---

## 3. Get Available Times

Get available appointment times for a specific date, establishment, and service duration.

### Endpoint
```
GET /api/bookings/availableTime
```

### Authentication
```
Authorization: Bearer ToKenBookingAuth123%
```

### Query Parameters
| Parameter | Type | Required | Format | Description |
|-----------|------|----------|--------|-------------|
| `date` | string | Yes | `YYYY-MM-DD` | Appointment date |
| `establishmentId` | string | Yes | ObjectId | Establishment ID from step 2 |
| `duration` | number | Yes | minutes | Service duration (from service data) |
| `services` | string | Yes | JSON array string | Service IDs as JSON: `["id1","id2"]` |

### cURL Example
```bash
curl -X GET "https://tempobook.virtusproject.com/api/bookings/availableTime?date=2025-12-22&establishmentId=6904e2236a90ec17427acc27&duration=10&services=%5B%2269442129eb76a386e5d4371f%22%5D" \
  -H "Authorization: Bearer ToKenBookingAuth123%"
```

### URL Encoded Parameters
```
date=2025-12-22
establishmentId=6904e2236a90ec17427acc27
duration=10
services=["69442129eb76a386e5d4371f"]
```

### Response (200 OK)
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

### Key Fields
| Field | Type | Description |
|-------|------|-------------|
| `availableTime` | array | List of available time slots |
| `availableTime[].time` | string | Time display format (HH:MM) |
| `availableTime[].startTime` | string | **Appointment start time (REQUIRED for booking)** |
| `availableTime[].endTime` | string | **Appointment end time (REQUIRED for booking)** |
| `availableTime[].duration` | number | Duration in minutes |
| `availableTime[].employees` | array | Employee IDs available at this time |
| `availableEmployees` | array | Full employee details |

---

## 4. Create Booking

Create a new appointment with all required information.

### Endpoint
```
POST /api/bookings/
```

### Authentication
```
Authorization: Bearer ToKenBookingAuth123%
```

### Request Body (JSON)
```json
{
  "customerInfo": {
    "email": "solm2508@gmail.com",
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

### cURL Example
```bash
curl -X POST "https://tempobook.virtusproject.com/api/bookings/" \
  -H "Authorization: Bearer ToKenBookingAuth123%" \
  -H "Content-Type: application/json" \
  -d '{
    "customerInfo": {
      "email": "solm2508@gmail.com",
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

### Required Fields
| Field | Path | Type | Description |
|-------|------|------|-------------|
| Email | `customerInfo.email` | string | Customer email |
| Name | `customerInfo.name` | string | Customer first name |
| Last Name | `customerInfo.lastName` | string | Customer last name |
| Phone | `customerInfo.phoneNumber` | string | Customer phone (without country code) |
| Phone Code | `customerInfo.phoneCode` | string | Country phone code (e.g., "+593") |
| Duration | `duration` | number | Total service duration in minutes |
| Services | `servicesSelected` | array | Array with service details |
| Establishment ID | `scheduleSelected.establishment._id` | string | Establishment ID |
| Date | `scheduleSelected.date` | string | Date in format `YYYY-MM-DD` |
| Start Time | `scheduleSelected.hour.startTime` | string | Start time in format `HH:MM` |
| End Time | `scheduleSelected.hour.endTime` | string | End time in format `HH:MM` |
| Employees | `scheduleSelected.hour.employees` | array | Array of available employee IDs |

### Response (201 Created)
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
      "email": "solm2508@gmail.com",
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
    "token": "...",
    "state": "Reservado",
    "createdAt": "2025-12-19T...",
    "updatedAt": "2025-12-19T..."
  }
}
```

### Error Responses

#### 400 Bad Request
```json
{
  "error": "Faltan campos obligatorios"
}
```

#### 500 Internal Server Error
```json
{
  "error": "Error internal"
}
```

Common causes:
- Missing required fields
- Invalid establishment ID
- Invalid employee ID
- Invalid service data
- Database constraint violations
- Employee not available at selected time

---

## Data Flow Summary

### Happy Path Flow

1. **User says**: "Quiero agendar bronceado"
   - Call **Get Services** → Extract Bronceado ID

2. **Call Get Establishments by Services**
   - Pass: Bronceado ID
   - Get: List of establishments offering that service with their IDs

3. **User selects**: "Quiero en FO"
   - Extract FO establishment ID from step 2 response

4. **User says date**: "22 de diciembre"
   - Call **Get Available Times**
   - Pass: FO ID, date, Bronceado duration (10 min), Bronceado ID

5. **User selects time**: "11:00"
   - Extract time slot details from step 4 response

6. **User provides info**: "Andres Martinez, email, phone"
   - Call **Create Booking**
   - Pass: All customer info + selected service + establishment + time slot

---

## Important Notes

### Establishment ID Tracking
- Extracted from step 2 response when displaying establishments
- Must be passed to step 3 (Get Available Times)
- Must be included in step 4 (Create Booking) with establishment name

### Schedule Object Format
The `scheduleSelected` object in Create Booking must include:
- `establishment` object with `_id` and `name`
- `date` in YYYY-MM-DD format
- `hour` object with:
  - `startTime` (from available times response)
  - `endTime` (from available times response)
  - `time` (display format)
  - `duration` (service duration)
  - `employees` array (available employee IDs)

### Services Array Format
Each service in `servicesSelected` must include:
- `_id`: Service ID
- `name`: Service name
- `duration`: Service duration
- `price`: Service price

---

## Test Data

### Available Services
```
Bronceado: 69442129eb76a386e5d4371f (10 min, Free)
Depilacion 2: 6944211deb76a386e5d4370f (20 min, Free)
Servicio general: 68714c066651248ada8c6c6c (7 min, $10)
```

### Available Establishments
```
FO: 6904e2236a90ec17427acc27
Shopping: 68714c066651248ada8c6c6e
```

### Available Employees (FO)
```
FO: 6904e2456a90ec17427acca0
```
