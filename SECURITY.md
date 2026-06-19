# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in the Ali robot project, please report it responsibly:

1. **DO NOT** open a public GitHub issue
2. Email: durdimatovm1904@gmail.com
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact

## Security Best Practices for Users

- Never commit `.env` files with API keys
- Use environment variables for all secrets
- Keep dependencies updated: `pip install --upgrade -r requirements.txt`
- Don't expose ESP32 serial port to untrusted networks
- Regularly rotate API keys (OpenRouter, etc.)

## Response Timeline

- Acknowledgment: within 48 hours
- Fix timeline: within 7 days for critical issues
