# Project completion checklist

This checklist distinguishes code present in the repository from work that requires a real account, a running service, or a human review. A file being present does not prove that the feature has passed an end-to-end run.

## Implemented in the repository

- [x] Customer, restaurant admin, kitchen, delivery partner, and superadmin app pages and API modules.
- [x] Ordering, JWT authentication, menu and dietary filtering, recommendations, conversational assistant fallback, demand forecasts, inventory alerts, kitchen queue, and restaurant analytics code.
- [x] Nearest eligible delivery partner assignment when a staff member confirms an order.
- [x] Delivery ETA calculation, GPS and demo location publishing, order-specific WebSocket tracking, Leaflet maps, and OSRM suggested routes.
- [x] Pytest test files, Postman v2.1 collection, Dockerfiles, Compose configuration, CI workflow, Terraform configuration, Gitflow guide, and a Figma design specification.

## Still required before calling the project complete

- [ ] Run the local application and follow a real order from customer checkout through kitchen, pickup, and delivery tracking.
- [x] Run `python -m pytest backend/tests -q` and fix any failing checks. The suite passed locally; rerun it in CI after pushing changes.
- [ ] Create the hosted high-fidelity Figma file and interactive prototype. Repository handoff assets now include `FIGMA_UI_UX_SPEC.md`, `FIGMA_IMPORT_GUIDE.md`, and a print-ready SVG wireframe.
- [ ] Push the project to GitHub, create/protect `main` and `develop`, configure `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`, and confirm the workflow succeeds.
- [ ] Build and run the Docker Compose stack on the target machine; confirm MySQL data persists after restarting containers.
- [ ] If AWS deployment is part of the submission, configure Terraform variables, review the plan and cost, apply it, then deploy the application. Terraform currently creates infrastructure and installs Docker; it does not itself deploy this application's containers.
- [ ] Activate a real payment-provider test account. Stripe Checkout and server-side payment verification are implemented; set `STRIPE_SECRET_KEY` and switch `PAYMENT_PROVIDER=stripe` to test or use the default sandbox mode.
- [ ] Add an LLM provider key only if LLM-generated replies are required; the assistant also has a local fallback.

## Suggested beginner run order

1. Start locally using the SQLite instructions in the project README.
2. Create a customer order, then sign in as kitchen staff and move it through preparation to ready.
3. Sign in as the delivery partner, accept the browser location prompt or use the simulation control, and confirm the customer map receives updates.
4. Run the pytest suite and resolve failures.
5. Create the Figma prototype and capture screenshots for the report.
6. Set up GitHub Actions and Docker Hub, then consider AWS deployment last.
