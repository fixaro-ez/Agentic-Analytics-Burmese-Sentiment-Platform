# 📊 Agentic Analytics & Burmese Sentiment Platform

## Capstone Project: End-to-End Data Mining, Data Warehousing, and AI Automation for the Myanmar Digital Ecosystem

## 1. Project Overview

This project is an end-to-end data pipeline and Agentic AI platform designed specifically to decode Burmese Sentiment within the Myanmar market. It extracts raw customer feedback from platforms like Facebook and Foodpanda and tackles the unique linguistic challenges of Myanmar (Unicode, legacy Zawgyi, and Burglish).

By utilizing a custom Two-Stage Aspect-Based Sentiment Analysis (ABSA) model, the system classifies Burmese text, stores analytical data in a PostgreSQL Data Warehouse, and surfaces insights via a BI Dashboard featuring "Chat with Data" and AI-driven autonomous alerts.

## 2. System Architecture

The architecture follows a modern ELT/ETL pipeline, leveraging both NoSQL and relational databases.

- **Data Ingestion:** Python scrapers extract dynamic DOM data from Facebook and API/DOM data from Foodpanda.
- **Data Lake (NoSQL):** Raw data is stored in MongoDB (`contents` and `feedbacks` collections) to handle schema flexibility.
- **AI Transformation (Burmese Sentiment ETL Layer):**
  - **Stage 1 ABSA:** Multi-label classification that detects six aspects, such as `customer_support` and `price_and_value`, in Burmese text.
  - **Stage 2 ABSA:** Sentence-pair classification that determines Positive, Negative, or Neutral sentiment for detected aspects.
- **Data Warehouse (RDBMS):** Cleaned, sentiment-scored data is loaded into PostgreSQL using a Star Schema with fact and dimension tables optimized for OLAP.
- **Presentation & Agentic Layer:** A React/Next.js frontend provides BI visualizations, while AI agents monitor the Data Warehouse for anomalies (for example, crisis alerts) and enable Text-to-SQL querying.

## 3. Academic Curriculum Mapping (15-Week Syllabus)

This project fulfills all major requirements of the Data Mining & Warehousing curriculum.

- **Weeks 1–3 — Data Exploration & Preparation:** Scraping, JSON handling, and exploratory data analysis of Burmese text nuances.
- **Weeks 4–5 — Preprocessing:** Burmese Unicode normalization, handling Zawgyi/Burglish noise, and removing "All-0" irrelevant rows.
- **Weeks 6–7 — Big Data & NoSQL:** MongoDB implementation for the Data Lake.
- **Weeks 8–9 — Data Warehousing & OLAP:** PostgreSQL Star Schema design and Sentiment ETL pipeline creation.
- **Weeks 10–11 — Association Rules:** Apriori/FP-Growth on aspects—for example, linking "Price" complaints to "Quality" complaints.
- **Weeks 12–13 — Classification & Evaluation:** XLM-RoBERTa ABSA models tailored for Burmese, evaluated using Precision, Recall, and F1-Score.
- **Weeks 14–15 — Cluster Analysis:** K-Means clustering of Facebook pages and Foodpanda shops based on their Burmese sentiment profiles.

## 4. Team Structure & Division of Labor (6 Members)

To ensure parallel development and equal contribution, the project is divided into specialized roles. Every member is responsible for testing and documenting their code.

### 🧑‍💻 Member 1: Data Engineering Lead (Scraping & NoSQL)

**Focus:** Data Acquisition and the Data Lake.

**Tasks:**

- Develop and maintain Playwright/Selenium scrapers for Facebook, handling dynamic DOM content and infinite scrolling.
- Develop scrapers/API extractors for Foodpanda.
- Design and manage the MongoDB `contents` and `feedbacks` collections.
- Implement proxy rotation and anti-ban mechanisms.

**Testing & QA:** Write unit tests for scrapers that simulate UI changes and validate MongoDB document structures.

**Documentation:** Document scraping logic, MongoDB schemas, and run instructions.

### 🧠 Member 2: Machine Learning Engineer (Burmese NLP & ABSA)

**Focus:** Natural Language Processing and Sentiment Model Training.

**Tasks:**

- Preprocess Burmese text through Unicode normalization and by handling Zawgyi encoding issues.
- Train the Stage 1 model for multi-label aspect detection using `xlm-roberta-base`, fine-tuned for Burmese with `BCEWithLogitsLoss`.
- Train the Stage 2 model for Positive/Negative/Neutral sentiment classification as a sentence-pair task.
- Perform hyperparameter tuning and export the model using ONNX or TorchScript.

**Testing & QA:** Generate confusion matrices, calculate F1/Precision/Recall scores, and test edge cases such as Burglish, mixed English-Burmese text, and local slang.

**Documentation:** Document the model architecture, training hyperparameters, handling of Burmese linguistic challenges, and evaluation metrics.

### 🏗️ Member 3: Data Warehouse Architect (ETL & PostgreSQL)

**Focus:** Data Transformation and Relational Storage.

**Tasks:**

- Design the PostgreSQL Star Schema with fact tables for Burmese sentiments and dimension tables for Time, Source, and Aspect.
- Write the Python ETL script that connects MongoDB, the NLP models, and PostgreSQL.
- Optimize SQL queries for OLAP operations such as roll-ups and drill-downs.

**Testing & QA:** Test the ETL pipeline for data loss, handle duplicate records, and ensure relational integrity in PostgreSQL.

**Documentation:** Provide the Data Dictionary, ERD (Entity-Relationship Diagram) for the Star Schema, and ETL workflow diagrams.

### 📊 Member 4: Data Scientist (Mining Algorithms & Analytics)

**Focus:** Academic Implementations (Weeks 10–15).

**Tasks:**

- Implement Association Rule Mining using the Apriori algorithm to find correlations between aspects in the PostgreSQL database.
- Implement K-Means or Hierarchical Clustering to group shops/pages based on their overall sentiment performance.
- Write Python scripts using scikit-learn and mlxtend to extract these insights periodically.

**Testing & QA:** Validate clustering silhouette scores and test association-rule confidence/support thresholds.

**Documentation:** Write the academic analysis report detailing findings, algorithmic choices, and the business value derived from the sentiment data.

### 🤖 Member 5: AI Agent & Backend Developer (FastAPI & LangChain)

**Focus:** Agentic Workflows and API Layer.

**Tasks:**

- Build a FastAPI backend to serve PostgreSQL sentiment data and Data Mining results to the frontend.
- Develop AI agent monitors that run periodically to detect sentiment spikes—for example, negative Burmese comments triggering a PR crisis alert—and send notifications.
- Implement the "Chat with Data" Text-to-SQL feature using LangChain and an LLM API.

**Testing & QA:** Test API endpoints using Postman/PyTest and rigorously test Text-to-SQL against prompt injection and destructive queries using read-only access.

**Documentation:** Provide Swagger/OpenAPI documentation and agent workflow diagrams.

### 💻 Member 6: Frontend Developer (UI/UX & Sentiment BI Dashboard)

**Focus:** Data Visualization and User Interface.

**Tasks:**

- Build the React/Next.js dashboard application.
- Create the Agentic Inbox: a unified feed prioritizing high-risk and urgent Burmese feedback flagged by AI.
- Build BI visualizations showing sentiment trends over time, aspect breakdowns, and clustering results using Recharts or Chart.js.
- Integrate the "Chat with Data" user interface.

**Testing & QA:** Perform cross-browser compatibility, responsive-design, and frontend state-management testing.

**Documentation:** Provide UI/UX wireframes, the component hierarchy, and user manuals.

## 5. Development Phases & Milestones

| Phase | Milestone | Primary Owners |
|---|---|---|
| Phase 1: Foundation | Scrapers active; MongoDB populated; Stage 1 ABSA dataset cleaned. | Members 1, 2 |
| Phase 2: Core NLP & DW | Burmese Sentiment Models trained; PostgreSQL Star Schema deployed. | Members 2, 3 |
| Phase 3: The Pipeline | ETL script connects MongoDB → Models → PostgreSQL successfully. | Member 3 |
| Phase 4: Analytics | API backend deployed; Data Mining algorithms (Clustering/Apriori) executed. | Members 4, 5 |
| Phase 5: Agentic UI | Frontend Dashboard live; Text-to-SQL working; Sentiment Alerts active. | Members 5, 6 |
| Phase 6: Final QA & Documentation | System-wide integration testing; final academic report compilation. | All Members |

## 6. Technology Stack

- **Scraping:** Python, Playwright, BeautifulSoup
- **Data Lake:** MongoDB
- **Machine Learning (Burmese NLP):** PyTorch, Hugging Face Transformers (`xlm-roberta`), scikit-learn
- **Data Warehouse & ETL:** PostgreSQL (Supabase), Python, SQLAlchemy/Psycopg2
- **Backend & Agents:** FastAPI, LangChain, OpenAI API (or Gemini/Claude)
- **Frontend:** React/Next.js, Tailwind CSS, Recharts
