import uvicorn
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Set
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum
import datetime

# # --- Database Setup (SQLite) ---

# DATABASE_URL = "sqlite:///./test.db"
# # Use check_same_thread=False only for SQLite.
# engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


DISK_MOUNT_PATH = "/var/data"
DATABASE_URL = f"sqlite:///{DISK_MOUNT_PATH}/test.db"

# Use check_same_thread=False for SQLite.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

class LinkPrecedence(enum.Enum):
    primary = "primary"
    secondary = "secondary"

class Contact(Base):
    __tablename__ = "contact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    phoneNumber: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    email: Mapped[Optional[EmailStr]] = mapped_column(String, nullable=True, index=True)
    
    # Foreign key to link to the primary contact
    linkedId: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contact.id"), nullable=True)
    
    linkPrecedence: Mapped[LinkPrecedence] = mapped_column(
        Enum(LinkPrecedence), default=LinkPrecedence.primary
    )
    
    createdAt: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updatedAt: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )
    
    # Relationship to query linked contacts
    # This defines the "one-to-many" relationship from a primary contact to its secondary contacts
    secondary_contacts = relationship("Contact", back_populates="primary_contact", foreign_keys=[linkedId])
    primary_contact = relationship("Contact", back_populates="secondary_contacts", remote_side=[id], foreign_keys=[linkedId])


# Create the database tables
Base.metadata.create_all(bind=engine)

# Dependency to get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Pydantic Models (API Request/Response) ---

class IdentifyRequest(BaseModel):
    email: Optional[EmailStr] = None
    phoneNumber: Optional[str] = None

class ContactResponseData(BaseModel):
    primaryContatctId: int # Note: The spec has a typo "ContatctId"
    emails: List[str]      # List of unique emails, primary first
    phoneNumbers: List[str] # List of unique phone numbers, primary first
    secondaryContactIds: List[int] # List of secondary contact IDs

class IdentifyResponse(BaseModel):
    contact: ContactResponseData


# --- FastAPI Application ---

app = FastAPI(
    title="Bitespeed Identity Reconciliation",
    description="API for the Bitespeed backend assessment task.",
)

@app.post("/identify", response_model=IdentifyResponse)
def identify_contact(
    request: IdentifyRequest, db: Session = Depends(get_db)
):
    """
    Reconciles contact information by linking accounts based on
    shared email addresses or phone numbers.
    """
    
    email = request.email
    phone_number = request.phoneNumber

    if not email and not phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either email or phoneNumber must be provided.",
        )

    # 1. Find all contacts matching the provided email or phone number
    matching_contacts = []
    if email:
        matching_contacts.extend(db.query(Contact).filter(Contact.email == email).all())
    if phone_number:
        matching_contacts.extend(db.query(Contact).filter(Contact.phoneNumber == phone_number).all())

    # Get unique contacts (in case both email and phone matched the same contact)
    unique_matching_contacts = list(dict.fromkeys(matching_contacts))

    if not unique_matching_contacts:
        # --- Scenario 1: No existing contacts found ---
        # Create a new primary contact
        new_contact = Contact(
            email=email,
            phoneNumber=phone_number,
            linkPrecedence=LinkPrecedence.primary
        )
        db.add(new_contact)
        db.commit()
        db.refresh(new_contact)
        
        response_data = ContactResponseData(
            primaryContatctId=new_contact.id,
            emails=[email] if email else [],
            phoneNumbers=[phone_number] if phone_number else [],
            secondaryContactIds=[]
        )
        return IdentifyResponse(contact=response_data)

    # --- Scenario 2 & 3: Existing contacts found ---
    
    # Find all unique primary contacts from the matched set
    # A contact is primary if it has no linkedId
    primary_contacts = sorted(
        [c for c in unique_matching_contacts if c.linkPrecedence == LinkPrecedence.primary],
        key=lambda c: c.createdAt
    )
    
    # Also find any secondary contacts and trace them back to their primary
    secondary_matches = [c for c in unique_matching_contacts if c.linkPrecedence == LinkPrecedence.secondary]
    for sec_contact in secondary_matches:
        if sec_contact.primary_contact and sec_contact.primary_contact not in primary_contacts:
            primary_contacts.append(sec_contact.primary_contact)
            
    # Ensure primary contacts are unique and sorted by creation date
    primary_contacts = sorted(
        list(dict.fromkeys(primary_contacts)),
        key=lambda c: c.createdAt
    )

    # The "main" primary contact will be the oldest one
    main_primary_contact = primary_contacts[0]

    # --- Scenario 3: Multiple primary contacts found ---
    # This means the request is linking two previously separate identities.
    # We must merge them: pick the oldest as the main primary,
    # and update the other(s) to be secondary.
    
    contacts_to_update = []
    if len(primary_contacts) > 1:
        for contact in primary_contacts[1:]:
            # Demote this primary contact to secondary
            contact.linkedId = main_primary_contact.id
            contact.linkPrecedence = LinkPrecedence.secondary
            contacts_to_update.append(contact)
            
            # Re-link all its children to the main primary contact
            for child in contact.secondary_contacts:
                child.linkedId = main_primary_contact.id
                contacts_to_update.append(child)
        
        db.add_all(contacts_to_update)

    # --- Check if new information is present ---
    # Do we need to create a new secondary contact?
    
    # Gather all current info from the entire identity group
    all_related_contacts = [main_primary_contact] + main_primary_contact.secondary_contacts + contacts_to_update
    
    existing_emails = {c.email for c in all_related_contacts if c.email}
    existing_phones = {c.phoneNumber for c in all_related_contacts if c.phoneNumber}

    # Check if the request contains new information
    new_email = email and email not in existing_emails
    new_phone = phone_number and phone_number not in existing_phones

    if new_email or new_phone:
        # Create a new secondary contact
        new_secondary_contact = Contact(
            email=email,
            phoneNumber=phone_number,
            linkedId=main_primary_contact.id,
            linkPrecedence=LinkPrecedence.secondary
        )
        db.add(new_secondary_contact)
        all_related_contacts.append(new_secondary_contact) # Add to list for response
    
    # Commit all changes (merges, new secondary contacts)
    db.commit()
    
    # --- Construct the final response ---
    
    # We need to refresh the main primary contact to get all its updated secondary_contacts
    db.refresh(main_primary_contact)
    
    # Gather all contacts in the consolidated group
    final_group = [main_primary_contact] + main_primary_contact.secondary_contacts
    
    # Collect all unique emails and phone numbers
    all_emails: Set[str] = set()
    all_phones: Set[str] = set()
    
    for c in final_group:
        if c.email:
            all_emails.add(c.email)
        if c.phoneNumber:
            all_phones.add(c.phoneNumber)
            
    # Format emails: primary's email first, then the rest
    ordered_emails = []
    if main_primary_contact.email:
        ordered_emails.append(main_primary_contact.email)
    ordered_emails.extend([e for e in all_emails if e != main_primary_contact.email])

    # Format phone numbers: primary's phone first, then the rest
    ordered_phones = []
    if main_primary_contact.phoneNumber:
        ordered_phones.append(main_primary_contact.phoneNumber)
    ordered_phones.extend([p for p in all_phones if p != main_primary_contact.phoneNumber])

    # Get all secondary contact IDs
    secondary_ids = [c.id for c in final_group if c.linkPrecedence == LinkPrecedence.secondary]
    
    response_data = ContactResponseData(
        primaryContatctId=main_primary_contact.id,
        emails=ordered_emails,
        phoneNumbers=ordered_phones,
        secondaryContactIds=sorted(list(set(secondary_ids))) # Ensure unique and sorted
    )
    
    return IdentifyResponse(contact=response_data)

