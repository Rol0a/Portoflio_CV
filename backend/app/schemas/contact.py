from pydantic import BaseModel, EmailStr, Field, field_validator


class ContactMessageCreate(BaseModel):
    """One contact-form submission.

    Length caps are deliberate: they bound what a single request can push into
    the owner's inbox, and they are validated before any SMTP connection is
    opened so an oversized body costs nothing to reject.
    """

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    message: str = Field(min_length=1, max_length=5000)

    # Honeypot. Real visitors never see this field (it is hidden and
    # aria-hidden in the form), so anything filled in came from a bot that
    # completes every input it finds. Named plausibly enough to be tempting.
    website: str = Field(default="", max_length=200)

    @field_validator("name", "message")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("name")
    @classmethod
    def _no_header_injection(cls, value: str) -> str:
        # Also enforced in contact_service before the header is built; rejected
        # here too so a hostile request never reaches the mail layer at all.
        if any(char in value for char in "\r\n"):
            raise ValueError("must not contain line breaks")
        return value


class ContactMessageResponse(BaseModel):
    status: str
