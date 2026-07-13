# FlowStater 
## From Operational Overhead to Enterprise Intelligence
FlowStater is an AI-powered knowledge management and collaboration platform designed to help organisations transform scattered information into structured, accessible, and actionable intelligence.

Built during the **AWS × UTP GenAI Hackathon 2026**, FlowStater addresses common enterprise challenges such as fragmented knowledge, inefficient document retrieval, communication gaps, and workflow uncertainty by combining secure document management with Generative AI assistance.

The platform enables organisations to securely store, manage, and retrieve internal knowledge while providing employees with an intelligent AI assistant that understands organisational context.


# Key Features
## 1. Secure Role-Based Access Control
FlowStater implements a clearance-driven access system to ensure sensitive information is only available to authorised users.

Features:
- Employee ID and password authentication
- Three-level access hierarchy:
  - **Level 1 — Staff**
  - **Level 2 — Manager**
  - **Level 3 — Executive**
- Documents are automatically filtered based on user clearance level
- Verified workflows improve information security and integrity

### Demo Credentials
| Employee | ID | Password | Access Level |
|---|---|---|---|
| Alex Chen | `0181460` | `0181460nat` | Level 1 — Staff |
| Natalie Ooi | `22011830` | `22011830nat` | Level 2 — Manager |
| Jordan Wu | `2538755` | `2538755nat` | Level 3 — Executive |


# 2. Intelligent Document Knowledge Library
FlowStater provides a centralised knowledge repository where employees can efficiently manage organisational documents.

Features:
- Shared document library based on user clearance
- Upload and download functionality
- Document ownership tracking through `owner_name`
- Structured storage for better information accessibility
- Automatic database schema migration support

All users with matching or higher clearance levels can access relevant documents, reducing information silos across teams.


# 3. Context-Aware AI Assistant
FlowStater integrates Generative AI to help employees interact with organisational knowledge more efficiently.

Features:
- Dedicated AI Assistant interface after login
- Maintains conversation history within sessions
- Powered by **Claude Sonnet 4.6** when API access is available
- Offline fallback mode for uninterrupted usage
- Backend AI endpoint:
```

POST /api/chat

````
The AI assistant helps users quickly understand information, ask questions, and improve decision-making efficiency.



# 4. Enterprise Workflow Intelligence

Beyond document storage, FlowStater aims to reduce operational overhead by turning organisational knowledge into actionable insights.
Potential applications:
- Faster information retrieval
- Improved internal communication
- Reduced time spent searching through documents
- AI-supported decision-making
- More efficient knowledge sharing across departments


# Brand Identity
**Project Name:** FlowStater
**Design System**
- Primary colours:
- Flame Orange `#ff4a13`
- Sky Blue `#83b4c2`
- Typography:
- Headings: Lora
- Body: Inter
- Visual identity:
- Hexagonal logo mark
- Gradient branding
- Modern dark-themed interface


# Getting Started
## Installation

Clone this repository:
```bash
git clone <repository-url>
cd FlowStater
````

Install dependencies:

```bash
pip install -r requirements.txt
```

## Enable AI Assistant (Optional)
To activate real-time AI responses, configure your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Run Application
```bash
python app.py
```

Open your browser:
```
http://localhost:5000
```

# Troubleshooting
### SQLite Column Error

If you encounter database schema errors, remove the existing database:

```bash
rm knowledge.db
```

The application will automatically recreate the database with the updated schema.

# Technology Stack
* **Frontend:** HTML, CSS, JavaScript
* **Backend:** Python
* **Database:** SQLite
* **AI Model:** Claude Sonnet 4.6
* **AI Framework:** Anthropic API
* **Development:** AWS × UTP GenAI Hackathon 2026



# Team
Developed as part of the **AWS × UTP GenAI Hackathon 2026**.
