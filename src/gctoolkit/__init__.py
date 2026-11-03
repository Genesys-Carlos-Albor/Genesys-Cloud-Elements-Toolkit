__version__ = "0.1.1"


def use_system_certificates() -> None:
    """Trust the OS certificate store, so HTTPS works behind corporate TLS inspection."""
    try:
        import truststore
    except ImportError:
        return
    truststore.inject_into_ssl()
