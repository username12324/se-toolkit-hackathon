# Screenshots

Placeholder files for README demo screenshots. Replace with actual screenshots before publishing.

## Required Screenshots

1. <img width="1917" height="808" alt="image" src="https://github.com/user-attachments/assets/df77bc68-2ba5-46f2-967f-36a72bf19fdf" />
 — Dashboard showing the Score Distribution bar chart and Task Pass Rates doughnut chart.
2. **dashboard-timeline-groups.png** — Dashboard showing the Submissions Timeline line chart and Group Performance bar chart.
3. **swagger-analytics.png** — Swagger UI (`/docs`) showing the analytics endpoints section.

## How to Capture

1. Start the services: `docker compose --env-file .env.docker.secret up --build -d`
2. Seed data: `curl -X POST http://localhost:42002/pipeline/sync -H "Authorization: Bearer <LMS_API_KEY>"`
3. Open the dashboard at `http://localhost:42002`, enter your API key, select a lab, and take screenshots.
4. Open Swagger UI at `http://localhost:42002/docs` and screenshot the analytics section.
