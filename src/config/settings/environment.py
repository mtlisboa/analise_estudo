def csv_values(raw_value: str) -> list[str]:
    """Return unique, non-empty values from a comma-separated setting."""
    return list(dict.fromkeys(value.strip() for value in raw_value.split(",") if value.strip()))


def csrf_origins(raw_value: str) -> list[str]:
    """Return only absolute HTTP(S) origins accepted by Django's CSRF setting."""
    return [
        origin
        for origin in csv_values(raw_value)
        if origin.startswith(("http://", "https://"))
    ]


def railway_origin(public_domain: str) -> str:
    """Convert Railway's host-only public domain into a trusted HTTPS origin."""
    domain = public_domain.strip().strip("/")
    if not domain:
        return ""
    return f"https://{domain}"
