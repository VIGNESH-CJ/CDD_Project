# AI Foodie

AI Foodie is a FastAPI food-ordering and restaurant-operations app. Its local quick start uses SQLite for convenience; Docker Compose runs the same SQLModel schema on MySQL 8.

## Run locally on Windows

Open PowerShell in this project folder (`CDD`) and run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn app.main:app --app-dir backend --reload
```

If PowerShell blocks virtual-environment activation, allow it for this terminal and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Open **http://127.0.0.1:8000**. The first startup creates the SQLite database at `database/aifoodie.db` and seeds the demo menu, restaurants, and accounts. API documentation is at **http://127.0.0.1:8000/docs**. Keep the terminal running while using the app; press `Ctrl+C` to stop it.

## Demo accounts

All demo accounts use password `Demo@12345`. You can use the one-click buttons on the login page.

| Role | Email |
| --- | --- |
| Customer | `customer@demo.com` |
| Restaurant admin | `admin@demo.com` |
| Kitchen staff | `kitchen@demo.com` |
| Delivery partner | `delivery@demo.com` |
| Super admin | `superadmin@demo.com` |

After signing in, each role is sent to its dashboard: customer (`/pages/customer-dashboard.html`), restaurant admin (`/pages/admin-dashboard.html`), kitchen (`/pages/kitchen-dashboard.html`), delivery partner (`/pages/delivery-dashboard.html`), or super admin (`/pages/superadmin-dashboard.html`). The home page is available at `/`.

### Add delivery partners

Sign in with the super admin account, open **User Management** in the super admin dashboard, and use **Add a delivery partner**. Enter the partner's name, email, initial password, and vehicle details. The account and delivery profile are created together, with availability set to offline. Share the initial password privately. The partner signs in through the normal login page and turns on availability from the delivery dashboard to receive assignments. Public registration remains customer-only.

## Optional configuration

The checked-in `.env.example` documents the environment variables. Copy it to `.env` to override defaults; the project already has a local `.env` configured for SQLite. SQLite is used by default, so MySQL is not required. AI API keys are optional; food assistance has a local fallback.

To use MySQL, install/start a MySQL server, set `DATABASE_URL` in `.env` to a valid SQLModel URL such as `mysql+pymysql://user:password@localhost:3306/aifoodie_db`, and restart the app.

### Optional conversational LLM

The food assistant uses the real menu and order database for its facts. To enable LLM-written replies, add either `OPENAI_API_KEY` or `GEMINI_API_KEY` to `.env` and restart the server. OpenAI is used when both are set. You can configure the OpenAI-compatible endpoint/model with `OPENAI_API_URL` and `OPENAI_MODEL`, or the Gemini endpoint with `GEMINI_API_URL`. With no key, or if the provider is unavailable, the existing local assistant replies are used. The LLM cannot create cart actions; the app keeps those tied to database results.

If the chat widget says **Live-menu assistant (local mode)**, it is working without a paid AI provider but uses simpler rules. To enable generated conversational replies, create an API key from your provider, add it to `.env` as `OPENAI_API_KEY=...` or `GEMINI_API_KEY=...`, and restart Uvicorn or recreate the backend container. Never put an API key in frontend JavaScript or commit `.env`. If you still see local mode after restart, check the backend terminal for a `Food assistant LLM request failed` warning; the app safely falls back to menu-based answers when the provider rejects a key or request.

The chat API is `POST /api/ai/chat` with JSON such as `{"message":"Suggest vegetarian food under ₹200"}`. An authenticated customer can also ask for their own order status. The server ignores a user ID supplied in the request body and uses the signed-in customer identity for that private lookup.

Historical demand forecasting uses Pandas to join and aggregate order-item history before training its Scikit-learn model.

## Tests

With the virtual environment active, run the existing backend test suite from the project root:

```powershell
python -m pytest backend/tests -q
```

The tests use a temporary in-memory SQLite database and do not replace the demo database.

## Payment providers

Online checkout is secure-provider ready and supports two modes:

- `PAYMENT_PROVIDER=sandbox` (default) creates a demo payment reference and does not charge real money.
- `PAYMENT_PROVIDER=stripe` creates a real Stripe Checkout session and verifies payment before confirming an order.

For Stripe test mode, set `STRIPE_SECRET_KEY` in `.env`. Never expose the secret key in frontend JavaScript.
# Delivery, deployment, and design additions

The live tracking implementation lives under the existing `backend/app` package. `PATCH /api/orders/{order_id}/status` assigns a nearest eligible delivery partner when an order becomes confirmed; accepting an order from the kitchen dashboard also attempts this assignment. Kitchen endpoints require an authenticated kitchen staff, restaurant admin, or super admin account, and restaurant admins are limited to their own restaurants. Kitchen actions must follow the order workflow, and handoff to delivery is rejected until a rider is assigned. Staff can also explicitly dispatch a confirmed order with `POST /api/delivery/orders/{order_id}/assign`. The authenticated ETA endpoint is `GET /api/delivery/orders/{order_id}/eta`; tracking metadata is `GET /api/delivery/orders/{order_id}/location`. Riders publish `{ "lat": 12.97, "lon": 77.59 }` to `/ws/delivery/{order_id}?token=<JWT>`, and customers connected to the same order receive location events.

The customer tracking map is in `frontend/pages/order-tracking.html` and `frontend/js/tracking.js`; the standalone rider demo is `frontend/delivery_partner.html`. Browser GPS requires HTTPS except on localhost. The simulation control is provided for local demonstration.

## Docker Compose

Copy `.env.example` to `.env`, set a strong unique `SECRET_KEY`, configure the MySQL password values, then run:

```bash
docker compose up --build
```

The frontend is served at `http://localhost/`; the backend API is available through the frontend reverse proxy and at container port 8000. MySQL data is stored in the `mysql_data` named volume. For local tests, the existing test fixtures use in-memory SQLite.

## CI and infrastructure

Configure repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` to publish backend and frontend images on pushes to `main`. Pull requests and pushes to `main` or `develop` run the pytest suite against a MySQL service container. For Terraform, set `key_name` and `allowed_ssh_cidr` in a local `terraform.tfvars`, then run `terraform init`, `terraform plan`, and `terraform apply` from `terraform/`. The AWS security group intentionally exposes 80 and 8000 as requested; restrict the API ingress to trusted CIDRs before production use.

See [the project completion checklist](docs/PROJECT_COMPLETION_CHECKLIST.md) for the difference between implementation files and steps that still require running services or external accounts.
