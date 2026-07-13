# FlowStater 

### 1. Login Page
First screen is a login with Employee ID + Password. Demo auto-fill buttons at the bottom.

**Demo credentials:**
| Employee | ID | Password | Access Level |
|---|---|---|---|
| Alex Chen | `0181460` | `0181460nat` | Level 1 — Staff |
| Natalie Ooi | `22011830` | `22011830nat` | Level 2 — Manager |
| Jordan Wu | `2538755` | `2538755nat` | Level 3 — Executive |

### 2. Shared Document Library
- All users at the same or higher clearance level can see uploaded documents
- Every document has a **Download** button — downloads as a .txt file
- Documents show who uploaded them (`owner_name` field added to DB)
- The DB schema auto-migrates — delete `knowledge.db` if you get column errors

### 3. Real AI Chatbox
- New **AI Assistant** tab (first page after login)  
- Maintains conversation history within the session  
- Uses `claude-sonnet-4-6` if `ANTHROPIC_API_KEY` is set  
- Falls back gracefully with a helpful offline message  
- New backend endpoint: `POST /api/chat`

### 4. FlowStater Branding
- **Name:** FlowStater
- **Colors:** `#ff4a13` (flame orange) + `#83b4c2` (sky blue)
- **Headings:** Lora (contemporary serif)
- **Body:** Inter (clean sans-serif)
- Hexagonal logo mark, gradient brand name, cohesive dark theme

## Run it

```bash
pip install -r requirements.txt

# Optional: real AI (strongly recommended)
export ANTHROPIC_API_KEY="sk-ant-..."

python app.py
```

Open http://localhost:5000

> **Note:** If you get a SQLite column error, delete `knowledge.db` so the DB re-creates with the new schema.
