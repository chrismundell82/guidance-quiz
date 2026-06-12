# AtkinsRéalis Guidance Notes Quiz

A fun, cheeky quiz for AtkinsRéalis bridge & structures engineers, testing knowledge across three difficulty levels.

## Structure

```
guidance-quiz/
├── app.py                              # Flask backend
├── Guidance_Notes_-_Quiz_Questions.xlsx  # Question bank (edit to update questions)
├── requirements.txt
├── Procfile
├── railway.toml
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    ├── js/quiz.js
    └── images/
        ├── happy.jpg
        ├── satisfied.jpg
        └── angry.jpg
```

## Updating Questions

Edit `Guidance_Notes_-_Quiz_Questions.xlsx`. The sheet must be named `Questions` with columns:
`Difficulty | Ref | Question | A | B | C | D | Answer`

- Difficulty values: `Guidance Guardian`, `Guidance Champion`, `Guidance God`
- Answer format: `A - text` (just the leading letter is used)

## Environment Variables (set in Railway)

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session secret (any random string) |
| `SMTP_HOST` | Optional | SMTP server for certificate emails |
| `SMTP_PORT` | Optional | SMTP port (default 587) |
| `SMTP_USER` | Optional | SMTP username/email |
| `SMTP_PASS` | Optional | SMTP password |
| `FROM_EMAIL` | Optional | Sender email address |

Email is optional — the quiz works fine without it; the certificate button will show an error if not configured.

## Deployment Steps (Railway)

See the deployment guide in the project documentation.
