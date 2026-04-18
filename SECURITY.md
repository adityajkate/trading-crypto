# Security Guidelines

## API Key Protection

**CRITICAL: Never commit API keys to version control**

### Setup Instructions

1. **Create secrets file** (not tracked by git):
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

2. **Add your credentials** to `.streamlit/secrets.toml`:
   ```toml
   BINANCE_TESTNET_API_KEY = "your_actual_key"
   BINANCE_TESTNET_API_SECRET = "your_actual_secret"
   ```

3. **Verify .gitignore** includes:
   ```
   .streamlit/secrets.toml
   ```

### Best Practices

- **Use Testnet First**: Always test with Binance testnet before using real funds
- **API Key Permissions**: Only enable necessary permissions (no withdrawal rights)
- **IP Restrictions**: Whitelist your IP address in Binance API settings
- **Regular Rotation**: Change API keys periodically
- **Monitor Usage**: Check API key activity regularly in Binance dashboard

### If Keys Are Exposed

1. **Immediately revoke** the exposed API keys in Binance
2. **Generate new keys** with proper restrictions
3. **Review account activity** for unauthorized access
4. **Update secrets.toml** with new credentials

### Environment Variables Alternative

For production deployments, use environment variables:

```bash
export BINANCE_TESTNET_API_KEY="your_key"
export BINANCE_TESTNET_API_SECRET="your_secret"
```

### Deployment Security

- Use Streamlit Cloud secrets management
- Never log API keys or secrets
- Implement rate limiting
- Use HTTPS for all API communications
- Keep dependencies updated

## Reporting Security Issues

If you discover a security vulnerability, please email security concerns privately rather than using public issues.
