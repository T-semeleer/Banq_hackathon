# bunq API Documentation

> Comprehensive reference guide for the bunq Public API — a full-featured banking API with 300+ operations for automating finances, managing accounts, processing payments, and building custom banking integrations.

**Base URLs:**

| Environment | Base URL |
|-------------|----------|
| Sandbox | `https://public-api.sandbox.bunq.com` |
| Production | `https://api.bunq.com` |

**Official Resources:**

- Documentation: [https://doc.bunq.com](https://doc.bunq.com)
- Developer Portal: [https://developer.bunq.com/portal](https://developer.bunq.com/portal)
- Postman Collection: [https://github.com/bunq/postman](https://github.com/bunq/postman)
- Status Page: [https://status.bunq.com](https://status.bunq.com)

---

## Table of Contents

1. [Core Concepts](#1-core-concepts)
2. [Authentication & API Context](#2-authentication--api-context)
3. [API Keys](#3-api-keys)
4. [OAuth Integration](#4-oauth-integration)
5. [Request Signing](#5-request-signing)
6. [Headers](#6-headers)
7. [API Objects](#7-api-objects)
   - [User](#71-user)
   - [Monetary Account](#72-monetary-account)
   - [Payment](#73-payment)
   - [RequestInquiry](#74-requestinquiry)
   - [Card](#75-card)
   - [Attachments](#76-attachments--notes)
8. [Callbacks (Webhooks)](#8-callbacks-webhooks)
9. [Pagination](#9-pagination)
10. [Querying Payments](#10-querying-payments)
11. [Errors & Response Codes](#11-errors--response-codes)
12. [Rate Limits](#12-rate-limits)
13. [Response Body Formatting](#13-response-body-formatting)
14. [IP Whitelisting](#14-ip-whitelisting)
15. [Geolocation](#15-geolocation)
16. [Moving to Production](#16-moving-to-production)
17. [PSD2 (Open Banking)](#17-psd2-open-banking)
18. [User Provisioning](#18-user-provisioning)
19. [API Reference — Full Endpoint Index](#19-api-reference--full-endpoint-index)
20. [Sandbox Environment](#20-sandbox-environment)

---

## 1. Core Concepts

The bunq API is organized around a small set of interrelated objects. Nearly every endpoint begins with `/user`, making the User object the root of all operations.

**Object hierarchy:**

```
User (user-person / user-company / user-payment-service-provider)
├── Monetary Account (bank accounts)
│   ├── Payment (transactions)
│   ├── RequestInquiry (payment requests)
│   ├── Draft Payment (pending approvals)
│   ├── Schedule (recurring payments)
│   └── Notification Filter (webhooks per account)
├── Card (debit/credit cards)
│   └── PIN Assignment
├── OAuth Client
│   └── Callback URLs
├── Attachment
└── Notification Filter (webhooks per user)
```

**Key principles:**

- All money lives in Monetary Accounts — every transaction flows through them.
- Payments can be outgoing (you send) or incoming (you receive); both are represented by the same Payment object.
- API keys are bound to devices and IP addresses for security.
- Sessions expire based on the auto-logout time set in the bunq app.
- Signing is required only for payment-creating and session-creating operations.

---

## 2. Authentication & API Context

bunq uses a multi-layered authentication system. Before making any standard API calls, you must establish an **API context** through three sequential steps:

### Step 1: Create an Installation

Register your public key with bunq. This is a one-time operation per API key.

```
POST /v1/installation
```

**Request body:**

```json
{
  "client_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
}
```

**Response contains:**

- `Id` — the installation ID
- `Token` — the **installation token** (used in Steps 2 and 3)
- `ServerPublicKey` — bunq's public key (store this for response signature verification)

> **Note:** This is the only endpoint that does not require the `X-Bunq-Client-Authentication` header.

### Step 2: Register a Device

Bind the API key to a device and its IP address(es).

```
POST /v1/device-server
```

**Headers:**

```
X-Bunq-Client-Authentication: {installation_token}
```

**Request body:**

```json
{
  "description": "My Server",
  "secret": "{your_api_key}",
  "permitted_ips": ["1.2.3.4"]
}
```

**Parameters:**

| Field | Description |
|-------|-------------|
| `description` | A human-readable label for your device |
| `secret` | Your API key |
| `permitted_ips` | Array of IPv4/IPv6 addresses allowed to use this API key. Pass `["*"]` for wildcard (must be enabled in app) |

**Response contains:**

- `Id` — the device-server ID

> **Important:** When using a standard API key, the device server and installation are locked to the IP address where they were created. A **Wildcard API Key** allows calls from any IP after registration.

### Step 3: Start a Session

Open an authenticated session to make API calls.

```
POST /v1/session-server
```

**Headers:**

```
X-Bunq-Client-Authentication: {installation_token}
X-Bunq-Client-Signature: {signature_of_request_body}
```

**Request body:**

```json
{
  "secret": "{your_api_key}"
}
```

**Response contains:**

- `Id` — session ID
- `Token` — the **session token** (use this for all subsequent API calls)
- `UserPerson` or `UserCompany` — your user object with user ID

### Session Lifecycle

- The **auto-logout time** set in the bunq app applies to all sessions, including API sessions.
- If a request is made within **30 minutes of session expiration**, the session is **automatically extended**.
- Use the session token from Step 3 as the `X-Bunq-Client-Authentication` header for all regular API calls.

### Authentication Token Usage Summary

| Endpoint | Token to Use |
|----------|-------------|
| `POST /v1/installation` | None required |
| `POST /v1/device-server` | Installation token |
| `POST /v1/session-server` | Installation token |
| All other endpoints | Session token |

---

## 3. API Keys

API keys are the primary credential for authenticating with the bunq API. They act as secret identifiers for your application.

### Obtaining a Sandbox API Key

**Via cURL:**

```bash
# Create a personal sandbox user
curl --location --request POST \
  'https://public-api.sandbox.bunq.com/v1/sandbox-user-person'

# Create a business sandbox user
curl --location --request POST \
  'https://public-api.sandbox.bunq.com/v1/sandbox-user-company'
```

**Response:**

```json
{
  "Response": [
    {
      "ApiKey": {
        "api_key": "sandbox_a918ac413524f2bf56ceb740595e01839dd7f0321ca08e4c4ea93349"
      }
    }
  ]
}
```

**Via Developer Portal:**

1. Log in at [developer.bunq.com/portal](https://developer.bunq.com/portal)
2. Authenticate with the bunq app
3. Navigate to "Sandbox users"
4. Generate a new user

### Obtaining a Production API Key

1. Open the bunq app
2. Go to **Settings → Developers → API keys**
3. Tap **Add API key**

> ⚠️ **Warning:** A production API key can control your bank account and make payments on your behalf. Guard it carefully and never commit it to source control. If compromised, revoke it immediately from the bunq app.

### API Key Types

| Type | IP Restriction | How to Enable |
|------|---------------|---------------|
| Standard | Bound to the IP used during device registration | Default behavior |
| Wildcard | Allows calls from any IP after `POST /device-server` | Enable "Allow All IP Addresses" in API Key menu in bunq app |

---

## 4. OAuth Integration

OAuth allows your application to request access to a bunq user's account. If the user grants permission, your app receives an access token that functions similarly to an API key but with predefined scopes.

> **Note:** Depending on your use case, you may need a **PSD2 permit** to access sensitive financial data or initiate payments on behalf of users.

### OAuth Flow

#### Step 1: Register an OAuth Client

Create an app in [bunq Developer](https://developer.bunq.com/portal) and add at least one Redirect URL.

**API alternative:**

```
POST /v1/user/{userId}/oauth-client
```

Then add callback URLs:

```
POST /v1/user/{userId}/oauth-client/{oauthClientId}/callback-url
```

```json
{
  "url": "https://yourapp.com/callback"
}
```

#### Step 2: Get OAuth Credentials

Retrieve your `client_id` and `client_secret` from the app settings in bunq Developer.

#### Step 3: Redirect Users for Authorization

Send users to:

```
https://oauth.bunq.com/auth?response_type=code
  &client_id=YOUR_CLIENT_ID
  &redirect_uri=https://yourapp.com/callback
  &state=unique_random_string
```

| Parameter | Description |
|-----------|-------------|
| `response_type` | Always `code` |
| `client_id` | Your OAuth client ID |
| `redirect_uri` | Must match a registered redirect URL |
| `state` | Random string for CSRF protection |

#### Step 4: Exchange Authorization Code for Access Token

After the user authorizes, they are redirected to your `redirect_uri` with a `code` parameter.

```bash
curl -X POST https://api.oauth.bunq.com/v1/token \
  -d grant_type=authorization_code \
  -d code=AUTH_CODE \
  -d redirect_uri=https://yourapp.com/callback \
  -d client_id=YOUR_CLIENT_ID \
  -d client_secret=YOUR_CLIENT_SECRET
```

**Sandbox token endpoint:** `https://oauth.sandbox.bunq.com/token`

Store the returned `access_token` in your database, associated with your end-user.

#### Step 5: Use the Access Token to Get a Session

The access token cannot be used directly for API calls. Use it as the `secret` in a session-server call:

```bash
curl -X POST https://api.bunq.com/v1/session-server \
  -H "Content-Type: application/json" \
  -H "Cache-Control: no-cache" \
  -H "User-Agent: my-app-name" \
  -H "X-Bunq-Language: en_US" \
  -H "X-Bunq-Region: nl_NL" \
  -H "X-Bunq-Geolocation: 0 0 0 0 000" \
  -H "X-Bunq-Client-Authentication: {installation_token}" \
  -H "X-Bunq-Client-Signature: {signature}" \
  -d '{"secret":"USER_ACCESS_TOKEN"}'
```

The resulting session token is then used for all subsequent API calls on behalf of that user.

#### Step 6: Make API Calls on Behalf of Users

```bash
curl -X GET \
  "https://public-api.sandbox.bunq.com/v1/user/{user_apikey_id}/monetary-account-bank" \
  -H "User-Agent: my-app" \
  -H "X-Bunq-Client-Authentication: {session_token}" \
  -H "Content-Type: application/json"
```

### OAuth Workflow Summary

```
1. User clicks "Connect" in your app
2. Redirect to bunq OAuth authorization URL
3. User grants permission in bunq
4. bunq redirects back with authorization code
5. Exchange code for access_token (store in DB)
6. Use access_token to create session → get session_token
7. Use session_token for API calls on behalf of user
```

---

## 5. Request Signing

bunq uses asymmetric cryptography to protect the integrity of certain API requests. Signing ensures that payment data has not been tampered with in transit.

### When Signing is Required

Signing is mandatory for:

- **Any request that creates or accepts a payment**
- **Session creation** (`POST /v1/session-server`)

If you forget to sign a request that requires it, the API returns error code **466** (`REQUEST SIGNATURE REQUIRED`).

> **Note:** Since April 28, 2020, bunq only validates the signature of the **request body**. URL and header signatures are no longer required.

### How Signing Works

1. Take the exact JSON request body as a string
2. Create a SHA256 hash signature using your **private key** with **PKCS #1 v1.5 padding**
3. Base64-encode the resulting signature
4. Add it as the `X-Bunq-Client-Signature` header

### Example (PHP)

```php
openssl_sign($requestBody, $signature, $privateKey, OPENSSL_ALGO_SHA256);
$encodedSignature = base64_encode($signature);
// Add to header: X-Bunq-Client-Signature: $encodedSignature
```

### Example (Python)

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import base64

signature = private_key.sign(
    request_body.encode('utf-8'),
    padding.PKCS1v15(),
    hashes.SHA256()
)
encoded_signature = base64.b64encode(signature).decode('utf-8')
```

### Example cURL

```bash
curl --location \
  'https://public-api.sandbox.bunq.com/v1/user/{userId}/monetary-account/{accountId}/payment' \
  --header 'X-Bunq-Client-Signature: eMymd9ynLx+j5tpc...==' \
  --header 'X-Bunq-Client-Authentication: {session_token}' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "amount": {"value": "0.10", "currency": "EUR"},
    "counterparty_alias": {"type": "EMAIL", "value": "user@example.com", "name": "Recipient"},
    "description": "My payment description"
  }'
```

### Verifying Response Signatures

bunq signs its responses using the server's private key. You can verify responses using the **server public key** received during installation:

1. Take the response body
2. Decode the Base64 signature from the `X-Bunq-Server-Signature` header
3. Verify using the server's public key with SHA256 + PKCS #1 v1.5

### Signing Troubleshooting Checklist

- Do you have a valid RSA key pair generated?
- Are you using the correct algorithms? (SHA256 hash + PKCS #1 v1.5 padding)
- Are you signing **only** the request body? (No headers, no URLs)
- Is the signature Base64-encoded before sending?
- Are there any extra spaces, trailing line breaks, or formatting changes in the body?
- Is the body you sign byte-for-byte identical to what you send?
- Have you added the full body to the data to sign (not just part of it)?

> **Tip:** The bunq SDKs handle signing automatically. If signing is causing issues, consider using an SDK.

---

## 6. Headers

### Mandatory Request Headers

| Header | Example | Description |
|--------|---------|-------------|
| `Cache-Control` | `no-cache` | Standard HTTP cache control. Required for all requests. |
| `User-Agent` | `bunq-TestServer/1.00 sandbox/0.17b3` | Identifies your application. No restrictions on format. |
| `X-Bunq-Client-Authentication` | `622749ac8b00c817...` | The authentication token. Use **installation token** for `/device-server` and `/session-server`; use **session token** for all other calls. Not required for `POST /v1/installation`. |
| `X-Bunq-Client-Signature` | `XLOwEdyjF1d+...` | Base64-encoded SHA256 signature of the request body. Required for payment and session creation endpoints. |

### Optional Request Headers

| Header | Example | Description |
|--------|---------|-------------|
| `X-Bunq-Language` | `en_US` | Preferred language. Supported: `en_US`, `nl_NL`. Default: `en_US`. Format: ISO 639-1 + ISO 3166-1 alpha-2, underscore-separated. |
| `X-Bunq-Region` | `nl_NL` | Client device region. Same format as language header. Used for localization. |
| `X-Bunq-Client-Request-Id` | `a4f0de` | Unique ID per request per logged-in user. Server rejects duplicate IDs on the same DeviceServer. Free-format. |
| `X-Bunq-Geolocation` | `4.89 53.2 12 100 NL` | Device geolocation. Format: `longitude latitude altitude radius country_code`. Use `0 0 0 0 000` when unknown. |

### Attachment Headers

| Header | Example | Description |
|--------|---------|-------------|
| `Content-Type` | `image/jpeg` | MIME type of the attachment. Supported: `image/png`, `image/jpeg`, `image/gif`. |
| `X-Bunq-Attachment-Description` | `Receipt photo` | Human-readable description of the attachment. |

### Response Headers

| Header | Description |
|--------|-------------|
| `X-Bunq-Client-Request-Id` | Echoed from request. Included in response signature for request-response pairing. |
| `X-Bunq-Client-Response-Id` | Unique UUID for the response. Use for replay attack protection. |
| `X-Bunq-Server-Signature` | Base64-encoded server signature of the response body. Verify with the server public key from installation. |

---

## 7. API Objects

### 7.1 User

The User is the root object in the bunq API. Almost every endpoint starts with `/user`.

**User types:**

| Type | Endpoint | Description |
|------|----------|-------------|
| `user-person` | `/user-person` | Individual users |
| `user-company` | `/user-company` | Business users |
| `user-payment-service-provider` | `/user-payment-service-provider` | PSD2-certified third-party providers |

The generic `/user` endpoint acts as a smart wrapper over all types. A `GET /user` request after opening a session returns your specific user ID and type.

**What a user can do:**

- Create monetary accounts (bank accounts)
- Manage cards
- Send and receive payments
- Create payment requests
- Set up notification filters (webhooks)
- Manage OAuth clients

**Key endpoint:**

```
GET /v1/user
```

Returns the full user object including notification filters, avatar, and legal information.

### 7.2 Monetary Account

A Monetary Account represents a bank account in bunq. Users can have multiple accounts of different types.

**Account types:**

| Type | Description |
|------|-------------|
| `MonetaryAccountBank` | Standard bunq bank account. Fully featured. |
| `MonetaryAccountJoint` | Shared account between two or more users. |
| `MonetaryAccountSavings` | Savings account with interest. Limited to 2 withdrawals/month. |
| `MonetaryAccountExternal` | Linked account from another bank. View-only (balance + transactions). |
| `MonetaryAccountExternalSavings` | External savings account from another bank. |
| `MonetaryAccountCard` | Prepaid cards or card-only products with limited banking features. |

**Key endpoints:**

```
GET  /v1/user/{userId}/monetary-account
GET  /v1/user/{userId}/monetary-account-bank/{accountId}
POST /v1/user/{userId}/monetary-account-bank
PUT  /v1/user/{userId}/monetary-account-bank/{accountId}
```

**Common fields:** `id`, `description`, `balance`, `status`, `currency`, `created`, `updated`

### 7.3 Payment

The Payment object represents all transactions — both incoming and outgoing — flowing through Monetary Accounts.

**Payment endpoints by type:**

| Endpoint | Description |
|----------|-------------|
| `POST /user/{userId}/monetary-account/{accountId}/payment` | Single payment |
| `POST .../payment-batch` | Batch of payments in one request |
| `POST .../draft-payment` | Payment requiring approval |
| `POST .../schedule-payment` | Scheduled (recurring) payment |
| `POST .../schedule-payment-batch` | Batch of scheduled payments |

**Creating a payment:**

```
POST /v1/user/{userId}/monetary-account/{accountId}/payment
```

```json
{
  "amount": {
    "value": "10.00",
    "currency": "EUR"
  },
  "counterparty_alias": {
    "type": "IBAN",
    "value": "NL02BUNQ1234567890",
    "name": "Recipient Name"
  },
  "description": "Payment description"
}
```

**Counterparty alias types:** `IBAN`, `EMAIL`, `PHONE_NUMBER`

**Key response fields:**

| Field | Description |
|-------|-------------|
| `id` | Unique payment ID |
| `amount` | Negative for outgoing, positive for incoming |
| `description` | Max 140 chars for external IBANs, 9000 chars for bunq-to-bunq |
| `alias` | Sender information |
| `counterparty_alias` | Recipient information |
| `type` | Payment type (e.g., `BUNQ`, `IDEAL`, `EBA_SCT`) |
| `monetary_account_id` | Account the payment belongs to |
| `balance_after_mutation` | Account balance after this transaction |
| `created` / `updated` | Timestamps |

**Example response (abbreviated):**

```json
{
  "Response": [{
    "Payment": {
      "id": 26174613,
      "created": "2025-07-21 09:16:50.008916",
      "amount": {"currency": "EUR", "value": "-0.10"},
      "description": "test",
      "type": "BUNQ",
      "alias": {"iban": "NL51BUNQ2093937468", "display_name": "A. Visser"},
      "counterparty_alias": {"iban": "NL32BUNQ2025313705", "display_name": "Sugar Daddy"},
      "balance_after_mutation": {"currency": "EUR", "value": "999.90"}
    }
  }]
}
```

### 7.4 RequestInquiry

A RequestInquiry is a payment request — asking another user to send you money. It is tied to a Monetary Account.

**Key endpoints:**

```
POST /v1/user/{userId}/monetary-account/{accountId}/request-inquiry
GET  /v1/user/{userId}/monetary-account/{accountId}/request-inquiry
GET  /v1/user/{userId}/monetary-account/{accountId}/request-inquiry/{requestId}
```

**Creating a request:**

```json
{
  "amount_inquired": {"value": "15.00", "currency": "EUR"},
  "counterparty_alias": {"type": "EMAIL", "value": "friend@example.com"},
  "description": "Dinner split",
  "allow_bunqme": false
}
```

**Optional fields:** `merchant_reference`, `redirect_url`, `minimum_age`, `require_address`, `address_shipping`, `address_billing`, `attachment`

**Status values:** `ACCEPTED`, `PENDING`, `REJECTED`, `EXPIRED`, `REVOKED`

**RequestResponse** — the counterpart object the recipient sees:

```
GET /v1/user/{userId}/monetary-account/{accountId}/request-response
PUT /v1/user/{userId}/monetary-account/{accountId}/request-response/{responseId}
```

Status values for responses: `ACCEPTED`, `PENDING`, `REJECTED`, `REFUND_REQUESTED`, `REFUNDED`, `REVOKED`

### 7.5 Card

bunq allows managing debit and credit cards through the API.

**Key endpoints:**

```
GET  /v1/user/{userId}/card
GET  /v1/user/{userId}/card/{cardId}
POST /v1/user/{userId}/card-debit
PUT  /v1/user/{userId}/card/{cardId}
```

**Card object fields (subset):**

| Field | Description |
|-------|-------------|
| `id` | Card ID |
| `type` | e.g., `MASTERCARD` |
| `product_type` | e.g., `MASTERCARD_DEBIT` |
| `status` | `ACTIVE`, `DEACTIVATED`, `LOST`, `STOLEN` |
| `card_limit` | Spending limit (amount object) |
| `card_limit_atm` | ATM withdrawal limit |
| `expiry_date` | Card expiration date |
| `pin_code_assignment` | PIN linked to monetary account(s) |
| `country_permission` | Countries where the card can be used |
| `name_on_card` | Name printed on the card |

**Card transactions** appear as regular Payment records:

```
GET /v1/user/{userId}/monetary-account/{accountId}/payment
```

For card-specific transaction details, use the **Mastercard Action** endpoint:

```
GET /v1/user/{userId}/monetary-account/{accountId}/mastercard-action
```

### 7.6 Attachments & Notes

**Uploading an attachment:**

```
POST /v1/user/{userId}/attachment-user
```

Headers: `Content-Type: image/jpeg`, `X-Bunq-Attachment-Description: "description"`

Body: raw binary image data

**Public attachments** (accessible without authentication):

```
POST /v1/attachment-public
```

**Note Text** — add text notes to various objects:

```
POST /v1/user/{userId}/monetary-account/{accountId}/payment/{paymentId}/note-text
```

```json
{
  "content": "This note is attached to the payment"
}
```

**Note Attachment** — attach files to objects:

```
POST /v1/user/{userId}/monetary-account/{accountId}/payment/{paymentId}/note-attachment
```

---

## 8. Callbacks (Webhooks)

Callbacks send real-time notifications when events occur on a bunq account.

### Setting Up Notification Filters

**URL notifications:**

```
POST /v1/user/{userId}/notification-filter-url
```

```json
{
  "notification_filters": [
    {
      "category": "PAYMENT",
      "notification_target": "https://yourserver.com/webhook"
    }
  ]
}
```

**Push notifications:**

```
POST /v1/user/{userId}/notification-filter-push
```

```json
{
  "notification_filters": [
    {
      "category": "SCHEDULE_RESULT"
    }
  ]
}
```

### Callback Categories

| Category | Description |
|----------|-------------|
| `BILLING` | All bunq invoices |
| `CARD_TRANSACTION_SUCCESSFUL` | Successful card transactions |
| `CARD_TRANSACTION_FAILED` | Failed card transactions |
| `CHAT` | Received chat messages |
| `DRAFT_PAYMENT` | Creation and updates of draft payments |
| `IDEAL` | iDEAL deposits to a bunq account |
| `SOFORT` | SOFORT deposits to a bunq account |
| `MUTATION` | Any action affecting a monetary account's balance |
| `OAUTH` | Revoked OAuth connections |
| `PAYMENT` | Payments created from or received on a bunq account (excludes Request, iDEAL, Sofort, Invoice payments). Outgoing = negative, incoming = positive. |
| `REQUEST` | Incoming requests and updates on outgoing requests |
| `SCHEDULE_RESULT` | When a scheduled payment is executed |
| `SCHEDULE_STATUS` | Status updates for scheduled payments (updated, cancelled) |
| `SHARE` | Updates or creation of Connects (ShareInviteBankInquiry) |
| `TAB_RESULT` | Updates on Tab payments |
| `BUNQME_TAB` | Updates on bunq.me Tab (open request) payments |
| `SUPPORT` | Messages received from bunq support |

### Mutation Category

A **Mutation** is any change in a monetary account's balance. It is created for every payment-like object (regular payment, request, iDEAL payment, etc.), making `MUTATION` the most comprehensive category for tracking balance changes.

### Callback IP Addresses

| Environment | Source IPs |
|-------------|-----------|
| Sandbox | Various AWS IP addresses |
| Production | `185.40.108.0/22` |

> IP addresses may change. bunq will notify in advance of planned changes.

### Removing Callbacks

Send an empty notification filters array:

```json
{
  "notification_filters": []
}
```

### Retry Mechanism

When a callback fails (server down, error response), bunq retries up to **5 additional times** with **1-minute intervals** between each attempt (6 total attempts).

**Listing failed callbacks:**

```
GET /v1/user/{userId}/notification-filter-failure
```

**Retrying failed callbacks:**

```
POST /v1/user/{userId}/notification-filter-failure
```

```json
{
  "notification_filter_failed_ids": "1,2,3"
}
```

Maximum of 100 IDs per retry request.

### Certificate Pinning

For added security, pin your server's SSL certificate so bunq validates it before sending callbacks.

**Retrieve your certificate:**

```bash
openssl s_client -servername www.example.com \
  -connect www.example.com:443 < /dev/null \
  | sed -n "/-----BEGIN/,/-----END/p" > www.example.com.pem
```

**Pin it:**

```
POST /v1/user/{userId}/certificate-pinned
```

> ⚠️ If your SSL certificate expires or changes, callbacks will fail until you update the pinned certificate.

---

## 9. Pagination

List endpoints support pagination via query parameters.

### Parameters

| Parameter | Default | Max | Description |
|-----------|---------|-----|-------------|
| `count` | 10 | 200 | Items per page |

**Example:**

```
GET /v1/user/1/monetary-account/1/payment?count=25
```

### Pagination Object

Every list response includes a `Pagination` object:

```json
{
  "Pagination": {
    "future_url": "/v1/.../payment?count=25&newer_id=249",
    "newer_url": "/v1/.../payment?count=25&newer_id=249",
    "older_url": "/v1/.../payment?count=25&older_id=224"
  }
}
```

| Field | Purpose | `null` means... |
|-------|---------|-----------------|
| `newer_url` | Next page (more recent items) | You're viewing the most recent items |
| `older_url` | Previous page (older items) | No older items exist |
| `future_url` | Check for new items added since this listing | You already have the latest item |

### Navigation Logic

- `newer_id` is always the ID of the **last** item in the current page
- `older_id` is always the ID of the **first** item in the current page
- Follow the provided URLs rather than constructing pagination parameters manually

---

## 10. Querying Payments

### List All Payments

```
GET /v1/user/{userId}/monetary-account/{accountId}/payment
GET /v1/user/{userId}/monetary-account/{accountId}/payment?count=25
```

### Get a Single Payment

```
GET /v1/user/{userId}/monetary-account/{accountId}/payment/{paymentId}
```

Returns full details including description, amounts, geolocation (if provided at creation), and attachments.

### Best Practices

- **Always paginate** when listing payments to manage memory and avoid rate limits
- **Use Pagination URLs** (`older_url`, `newer_url`) instead of manually constructing queries
- **Use Webhooks** for real-time updates instead of polling
- **Client-side filtering** is required — the API does not support filtering on `description`, `amount`, or custom metadata. Filter after retrieval.
- **Handle optional fields** gracefully — not all payments include `geolocation`, `attachments`, etc.
- **Cache frequently queried data** to reduce API usage
- **Respect rate limits** (see [Rate Limits](#12-rate-limits))

---

## 11. Errors & Response Codes

### HTTP Response Codes

| Code | Name | Description |
|------|------|-------------|
| 200 | OK | Successful request |
| 399 | NOT MODIFIED | Same as 304. You have a local cached copy. |
| 400 | BAD REQUEST | A parameter is missing or invalid |
| 401 | UNAUTHORISED | Token or signature is invalid |
| 403 | FORBIDDEN | You're not allowed to make this call |
| 404 | NOT FOUND | The requested object cannot be found |
| 405 | METHOD NOT ALLOWED | HTTP method not allowed for this endpoint |
| 429 | RATE LIMIT | Too many requests in too short a period |
| 466 | REQUEST SIGNATURE REQUIRED | Request signature is required for this operation |
| 490 | USER ERROR | A parameter is missing or invalid |
| 491 | MAINTENANCE ERROR | bunq is in maintenance mode |
| 500 | INTERNAL SERVER ERROR | Something went wrong on bunq's end |

All 4xx errors include a JSON body explaining what went wrong.

### Error Response Format

```json
{
  "Error": [
    {
      "error_description": "Error description in English",
      "error_description_translated": "User-facing error description (auto-translated)"
    }
  ]
}
```

The `error_description_translated` field is automatically translated based on the `X-Bunq-Language` header.

---

## 12. Rate Limits

Rate limits are enforced **per IP address per endpoint**:

| Method | Limit |
|--------|-------|
| `GET` | 3 requests per 3 consecutive seconds |
| `POST` | 5 requests per 3 consecutive seconds |
| `PUT` | 2 requests per 3 consecutive seconds |
| Callbacks | 2 callback URLs per notification category |

Exceeding these limits results in a **429** error. Implement exponential backoff or throttling in your application.

---

## 13. Response Body Formatting

### Standard Response Structure

All JSON responses have a top-level object with a `Response` array, even for single-object responses:

```json
{
  "Response": [
    {
      "DataObject": {}
    }
  ]
}
```

### Error Response Structure

```json
{
  "Error": [
    {
      "error_description": "Error explanation in English",
      "error_description_translated": "User-facing translated error"
    }
  ]
}
```

### Object Type Indications

When a field can contain different object types, they are nested in a discriminator object:

```json
{
  "Response": [{
    "ChatMessage": {
      "id": 5,
      "content": {
        "ChatMessageContentText": {
          "text": "Message text here"
        }
      }
    }
  }]
}
```

---

## 14. IP Whitelisting

IP whitelisting restricts which IP addresses can make API calls, adding a layer of security beyond the API key.

### Default Behavior

- The IP address used during device registration is automatically whitelisted and set to `ACTIVE`.
- If you pass `["*"]` during device registration, the API uses the calling IP.
- Wildcard (`*`) IP filtering can only be managed via the bunq app, not the API.

### Managing IP Addresses

**List credentials:**

```
GET /v1/user/{userId}/credential-password-ip
```

**List IPs for a credential:**

```
GET /v1/user/{userId}/credential-password-ip/{credentialId}/ip
```

**Add a new IP:**

```
POST /v1/user/{userId}/credential-password-ip/{credentialId}/ip
```

```json
{
  "ip": "203.0.113.50",
  "status": "ACTIVE"
}
```

**Update IP status:**

```
PUT /v1/user/{userId}/credential-password-ip/{credentialId}/ip/{ipId}
```

```json
{
  "status": "INACTIVE"
}
```

> **Important:** IP addresses cannot be changed once created. To update, mark the old one as `INACTIVE` and add a new one.

### IP Status Values

| Status | Description |
|--------|-------------|
| `ACTIVE` | IP is allowed to authenticate |
| `INACTIVE` | IP is blocked |

### Security Best Practices

- Regularly review and remove unused IPs
- Avoid wildcard (`*`) unless absolutely necessary
- Use `INACTIVE` instead of deleting for audit trails
- Use distinct credentials per environment (dev, staging, production)

---

## 15. Geolocation

The `X-Bunq-Geolocation` header allows bunq to associate geographic location data with API calls, particularly payments.

**Format:** `longitude latitude altitude radius country_code`

**Examples:**

```
X-Bunq-Geolocation: 4.89 53.2 12 100 NL
X-Bunq-Geolocation: 0 0 0 0 000   (when unknown)
```

| Component | Format | Description |
|-----------|--------|-------------|
| Longitude | Decimal | GPS longitude |
| Latitude | Decimal | GPS latitude |
| Altitude | Decimal | Altitude in meters |
| Radius | Decimal | Accuracy radius in meters |
| Country | ISO 3166-1 alpha-2 | Country code (e.g., `NL`) |

When no geolocation is available, the header must still be included with zero values.

---

## 16. Moving to Production

When your sandbox integration is fully tested:

1. **Generate a production API key** via the bunq app: *Profile → Security & Settings → Developers → API keys*
2. **Replace your API key** and repeat the authentication sequence (installation → device-server → session-server)
3. **Change the base URL** from `https://public-api.sandbox.bunq.com` to `https://api.bunq.com`

**Recommendations:**

- Use a **standard API key** (not wildcard) in production for security
- If your application accesses other users' account information or initiates payments on their behalf, you may need a **PSD2 permit**

---

## 17. PSD2 (Open Banking)

If you are a PSD2-certified Third Party Provider (TPP), bunq provides specific integration paths depending on your permit type.

### TPP Registration

Register as a TPP by sending your QSEAL certificate:

```
POST /v1/payment-service-provider-credential
```

The request must include:
- QSEAL certificate
- QSEAL certificate chain
- Signature of the device registration key with the QSEAL private key

The returned token acts as your API key.

### Provider Types

| Provider | Acronym | Capabilities |
|----------|---------|-------------|
| Account Information Service Provider | AISP | Read account data, balances, and transactions |
| Payment Initiation Service Provider | PISP | Initiate payments on behalf of users |
| Card-Based Payment Instrument Issuer | CBPII | Confirm availability of funds |

### Key Points

- The API is the same for regular users and PSD2 providers
- As a PSD2 party, you can only access endpoints corresponding to your permit level
- OAuth is used for user authorization (same flow as described in [Section 4](#4-oauth-integration))
- Request signing requirements are the same for all API user types

---

## 18. User Provisioning

User Provisioning is an advanced flow for creating and onboarding new bunq users programmatically. It follows a multi-chapter process:

### Chapter 0: Setting Up the API Context

Establish the API context (installation, device registration, session) as described in [Section 2](#2-authentication--api-context).

### Chapter 1: Setting Up OAuth Client

Create and configure an OAuth client for your application:

```
POST /v1/user/{userId}/oauth-client
POST /v1/user/{userId}/oauth-client/{oauthClientId}/callback-url
```

### Chapter 2: Creating a User Provision

Create a new user provision through the API, providing the required user details and documentation.

### Chapter 3: Onboarding

Guide the provisioned user through bunq's onboarding process, including identity verification and compliance checks.

### Chapter 4: Webhooks / Callbacks

Set up notification filters (webhooks) for the provisioned user to receive real-time updates about account events.

---

## 19. API Reference — Full Endpoint Index

The bunq API provides over 300 operations organized into the following endpoint groups:

| Endpoint Group | Description |
|---------------|-------------|
| Additional Transaction Information Category | Transaction categorization |
| Additional Transaction Information Category User Defined | Custom transaction categories |
| Attachment | User-level file attachments |
| Attachment Public | Publicly accessible attachments |
| Avatar | User and company avatar management |
| Billing Contract Subscription | Subscription and billing management |
| bunqme | bunq.me payment link management |
| Callback URL OAuth | OAuth redirect URL management |
| Cards | Card creation, listing, and management |
| Confirmation Of Funds | Fund availability checks (PSD2/CBPII) |
| Content and Exports | Content retrieval and data export |
| Credential Password IP | API credential and IP management |
| Currency Cloud | Multi-currency operations via CurrencyCloud |
| Currency Conversion | Currency exchange within bunq |
| Customer Statements | Account statement generation |
| Devices | Device registration and management |
| Draft Payment | Payments requiring approval before execution |
| Event | Event log and history |
| Exports | Data export operations |
| Generated CVC2 | Virtual CVC2 code generation for online payments |
| Ideal Merchant Transaction | iDEAL payment processing for merchants |
| Insights | Financial insights and analytics |
| Installation | API installation management |
| Invoice | Invoice management |
| Invoice Export | Invoice export operations |
| Legal Name | Legal name management |
| Limit | Account and card limit management |
| Mastercard Action | Mastercard transaction details |
| Monetary Account | Bank account management (all types) |
| Name | Display name management |
| Note Text & Attachment | Notes attached to API objects |
| Notification Filter | Webhook/push notification configuration |
| OAuth | OAuth client management |
| Payment | Payment creation, listing, and details |
| Payment Auto Allocation | Automatic payment distribution rules |
| Payment Service Provider | PSD2 provider management |
| Request | Payment request management (Inquiry + Response) |
| Sandbox Users | Sandbox user creation |
| Schedule | Scheduled/recurring payment management |
| Server Error | Server error information |
| Server Public Key | Server public key retrieval |
| Session | Session management |
| Sofort Merchant Transaction | SOFORT payment processing |
| Statement | Account statement operations |
| Switch Service Payment | Bank switch service payments |
| Token QR Request Sofort | QR-based SOFORT payment tokens |
| Transferwise | TransferWise (Wise) integration |
| Tree Progress | bunq tree-planting progress |
| User | User information and management |
| Whitelist SSD | SSD whitelist management |

---

## 20. Sandbox Environment

The sandbox provides a safe testing environment that mirrors production behavior.

### Sandbox Base URL

```
https://public-api.sandbox.bunq.com
```

### Creating Sandbox Users

```bash
# Personal user
curl -X POST 'https://public-api.sandbox.bunq.com/v1/sandbox-user-person'

# Business user
curl -X POST 'https://public-api.sandbox.bunq.com/v1/sandbox-user-company'
```

Each sandbox user gets a complete simulated bank profile with name, address, phone number, and an empty bank account.

### Getting Sandbox Money

Use the **Sugar Daddy** mechanism to get test funds. Send a RequestInquiry from your sandbox user to the Sugar Daddy sandbox user, and the request will be automatically accepted:

```
POST /v1/user/{userId}/monetary-account/{accountId}/request-inquiry
```

```json
{
  "amount_inquired": {"value": "500.00", "currency": "EUR"},
  "counterparty_alias": {"type": "EMAIL", "value": "sugardaddy@bunq.com"},
  "description": "Test funds",
  "allow_bunqme": false
}
```

### Sandbox App

You can log into the sandbox version of the bunq app with your sandbox user to visually verify operations and test the user experience.

### Key Differences from Production

| Aspect | Sandbox | Production |
|--------|---------|------------|
| Base URL | `public-api.sandbox.bunq.com` | `api.bunq.com` |
| API Key prefix | `sandbox_...` | No prefix |
| Real money | No | Yes |
| Callback IPs | Various AWS IPs | `185.40.108.0/22` |
| OAuth URL | `oauth.sandbox.bunq.com` | `oauth.bunq.com` |

---

## Appendix A: Quick-Start Checklist

```
[ ] Generate a sandbox API key (POST /v1/sandbox-user-person)
[ ] Generate an RSA key pair
[ ] Create installation (POST /v1/installation) → save installation token + server public key
[ ] Register device (POST /v1/device-server) → save device ID
[ ] Start session (POST /v1/session-server) → save session token + user ID
[ ] Make a GET /v1/user call to verify your session
[ ] List monetary accounts (GET /v1/user/{id}/monetary-account)
[ ] Request sandbox money from Sugar Daddy
[ ] Make your first payment (POST .../payment) — remember to sign!
[ ] Set up a webhook (POST .../notification-filter-url)
[ ] Move to production when ready
```

## Appendix B: Common cURL Templates

### Create Installation

```bash
curl -X POST https://public-api.sandbox.bunq.com/v1/installation \
  -H "Content-Type: application/json" \
  -H "User-Agent: my-app" \
  -d '{"client_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"}'
```

### Register Device

```bash
curl -X POST https://public-api.sandbox.bunq.com/v1/device-server \
  -H "Content-Type: application/json" \
  -H "User-Agent: my-app" \
  -H "X-Bunq-Client-Authentication: {installation_token}" \
  -d '{"description": "My Server", "secret": "{api_key}", "permitted_ips": ["*"]}'
```

### Start Session

```bash
curl -X POST https://public-api.sandbox.bunq.com/v1/session-server \
  -H "Content-Type: application/json" \
  -H "User-Agent: my-app" \
  -H "X-Bunq-Client-Authentication: {installation_token}" \
  -H "X-Bunq-Client-Signature: {signature}" \
  -d '{"secret": "{api_key}"}'
```

### List Accounts

```bash
curl -X GET \
  "https://public-api.sandbox.bunq.com/v1/user/{userId}/monetary-account" \
  -H "User-Agent: my-app" \
  -H "X-Bunq-Client-Authentication: {session_token}"
```

### Create Payment

```bash
curl -X POST \
  "https://public-api.sandbox.bunq.com/v1/user/{userId}/monetary-account/{accountId}/payment" \
  -H "Content-Type: application/json" \
  -H "User-Agent: my-app" \
  -H "X-Bunq-Client-Authentication: {session_token}" \
  -H "X-Bunq-Client-Signature: {signature}" \
  -d '{
    "amount": {"value": "10.00", "currency": "EUR"},
    "counterparty_alias": {"type": "EMAIL", "value": "recipient@example.com", "name": "Recipient"},
    "description": "Test payment"
  }'
```

---

*Documentation compiled from [doc.bunq.com](https://doc.bunq.com). For the most up-to-date information, always refer to the official bunq API documentation.*
