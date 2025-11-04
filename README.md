# 🏍️ RideReady — AI-Powered Motorcycle & Gear Recommender

> **Your personal riding assistant.**  
> RideReady helps new and casual riders discover motorcycles tailored to their needs through natural conversation — powered by **Flask**, **OpenAI GPT**, and **Google Image Search API**.

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)

---

## 🌟 Features

- 💬 **AI Chat Interface** — Talk naturally about your riding style, budget, and preferences.
- 🧠 **Intelligent Recommendations** — Uses OpenAI GPT to suggest beginner-friendly motorcycles.
- 🏍️ **Local + Google Image Resolver** — Matches bikes to curated local images, then falls back to Google for unmatched models.
- ⚙️ **Dockerized Deployment** — Production-ready with Gunicorn and GitHub Actions CI/CD.
- 🔒 **Environment-Driven Setup** — Secure key management via `.env` file.
- 🧩 **Modular Codebase** — Separate services for chat, image resolution, and recommendation logic.

---

## 🏗️ Architecture Overview

```mermaid
flowchart TD
    A[User Input 🧍] -->|Query| B[Flask API /api/chat]
    B --> C[Chat NLU - OpenAI gpt-4o-mini]
    C -->|Plan + Actions| D[_run_recommend()]
    D --> E[Image Resolver Service]
    E -->|Local JSON Lookup| F[static/images.json]
    E -->|Fallback| G[Google CSE API]
    G --> H[Result URLs]
    D --> I[Frontend Recommendation Cards]
    I --> J[Rendered Chat + Image Results]
