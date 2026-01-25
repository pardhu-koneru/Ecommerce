# Admin User Management Endpoints

All endpoints require **IsAdminUser** permission (user must have `is_staff=True`).

## Base URL
```
/api/admin/users/
```

## Endpoints

### 1. List All Users (Paginated & Filterable)
```
GET /api/admin/users/
```

**Query Parameters:**
- `page` (int): Page number (default: 1)
- `page_size` (int): Items per page (default: 10, max: 100)
- `search` (str): Search by email, username, first_name, last_name
- `ordering` (str): Order by field (`created_at`, `email`, `is_active`, `is_staff`)

**Example:**
```
GET /api/admin/users/?page=1&page_size=20&search=john&ordering=-created_at
```

**Response:**
```json
{
  "count": 42,
  "next": "http://localhost:8000/api/admin/users/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "email": "john@example.com",
      "username": "john_doe",
      "first_name": "John",
      "last_name": "Doe",
      "phone_number": "+1234567890",
      "email_verified": true,
      "is_active": true,
      "is_staff": false,
      "role": "user",
      "created_at": "2026-01-24T10:30:00Z"
    }
  ]
}
```

---

### 2. Get User Details
```
GET /api/admin/users/{id}/
```

**Example:**
```
GET /api/admin/users/1/
```

**Response:**
```json
{
  "id": 1,
  "email": "john@example.com",
  "username": "john_doe",
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+1234567890",
  "email_verified": true,
  "is_active": true,
  "is_staff": false,
  "role": "user",
  "created_at": "2026-01-24T10:30:00Z"
}
```

---

### 3. Create New User
```
POST /api/admin/users/
```

**Request Body:**
```json
{
  "email": "newuser@example.com",
  "username": "newuser",
  "first_name": "New",
  "last_name": "User",
  "phone_number": "+9876543210",
  "password": "SecurePassword123!",
  "is_staff": false,
  "is_active": true
}
```

**Response (201 Created):**
```json
{
  "id": 42,
  "email": "newuser@example.com",
  "username": "newuser",
  "first_name": "New",
  "last_name": "User",
  "phone_number": "+9876543210",
  "email_verified": false,
  "is_active": true,
  "is_staff": false,
  "role": "user",
  "created_at": "2026-01-24T12:00:00Z"
}
```

---

### 4. Update User (Full Update)
```
PUT /api/admin/users/{id}/
```

**Request Body (All fields required):**
```json
{
  "email": "updated@example.com",
  "username": "updated_user",
  "first_name": "Updated",
  "last_name": "User",
  "phone_number": "+1111111111",
  "password": "NewPassword123!",
  "email_verified": true,
  "is_active": true,
  "is_staff": true
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "updated@example.com",
  "username": "updated_user",
  "first_name": "Updated",
  "last_name": "User",
  "phone_number": "+1111111111",
  "email_verified": true,
  "is_active": true,
  "is_staff": true,
  "role": "admin",
  "created_at": "2026-01-24T10:30:00Z"
}
```

---

### 5. Update User (Partial Update)
```
PATCH /api/admin/users/{id}/
```

**Request Body (Fields optional):**
```json
{
  "first_name": "John",
  "last_name": "Updated",
  "is_staff": true
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "john@example.com",
  "username": "john_doe",
  "first_name": "John",
  "last_name": "Updated",
  "phone_number": "+1234567890",
  "email_verified": true,
  "is_active": true,
  "is_staff": true,
  "role": "admin",
  "created_at": "2026-01-24T10:30:00Z"
}
```

**Note:** Password field is optional in PATCH requests. Include it only if you want to change the password.

---

### 6. Delete User
```
DELETE /api/admin/users/{id}/
```

**Response (204 No Content):**
```
No response body
```

---

### 7. Activate User Account
```
PATCH /api/admin/users/{id}/activate/
```

**Response (200 OK):**
```json
{
  "msg": "User john@example.com has been activated"
}
```

---

### 8. Deactivate User Account
```
PATCH /api/admin/users/{id}/deactivate/
```

**Response (200 OK):**
```json
{
  "msg": "User john@example.com has been deactivated"
}
```

---

## Error Responses

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

### 403 Forbidden (Not Admin)
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### 400 Bad Request (Validation Error)
```json
{
  "email": ["This field may not be blank."],
  "password": ["This field is required."]
}
```

---

## Authentication

All requests require a Bearer token in the Authorization header:
```
Authorization: Bearer <access_token>
```

---

## Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | User ID (read-only) |
| `email` | string | Email address (unique, required) |
| `username` | string | Username (optional) |
| `first_name` | string | First name (optional) |
| `last_name` | string | Last name (optional) |
| `phone_number` | string | Phone number (optional) |
| `password` | string | Password (write-only, required on create) |
| `email_verified` | boolean | Email verification status (read-only in list/retrieve) |
| `is_active` | boolean | Account active status (default: true) |
| `is_staff` | boolean | Admin/Staff status (default: false) |
| `role` | string | User role - "admin" or "user" (read-only, computed) |
| `created_at` | datetime | Account creation timestamp (read-only) |

---

## Usage Examples

### Using cURL

**List users:**
```bash
curl -X GET "http://localhost:8000/api/admin/users/" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Create user:**
```bash
curl -X POST "http://localhost:8000/api/admin/users/" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "SecurePass123!",
    "first_name": "Test",
    "last_name": "User"
  }'
```

**Activate user:**
```bash
curl -X PATCH "http://localhost:8000/api/admin/users/1/activate/" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Using Python (requests library)

```python
import requests

BASE_URL = "http://localhost:8000/api/admin/users/"
HEADERS = {"Authorization": f"Bearer {access_token}"}

# List users
response = requests.get(BASE_URL, headers=HEADERS)
print(response.json())

# Create user
data = {
    "email": "test@example.com",
    "password": "SecurePass123!",
    "first_name": "Test"
}
response = requests.post(BASE_URL, json=data, headers=HEADERS)
print(response.json())

# Update user
data = {"first_name": "Updated"}
response = requests.patch(f"{BASE_URL}1/", json=data, headers=HEADERS)
print(response.json())

# Delete user
response = requests.delete(f"{BASE_URL}1/", headers=HEADERS)
```

---

## Filtering Examples

**Search for users:**
```
GET /api/admin/users/?search=john
```

**Filter by ordering:**
```
GET /api/admin/users/?ordering=-created_at  # Newest first
GET /api/admin/users/?ordering=email         # A-Z by email
```

**Pagination:**
```
GET /api/admin/users/?page=2&page_size=15
```

**Combined:**
```
GET /api/admin/users/?search=john&ordering=-created_at&page=1&page_size=20
```

---

## Notes

- All admin operations require `IsAdminUser` permission
- Passwords are write-only (never returned in responses)
- Email addresses must be unique
- The `role` field is automatically computed based on `is_staff` status
- Search is case-insensitive
- Pagination defaults to 10 items per page
- Maximum page size is 100 items
