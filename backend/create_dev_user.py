"""Create dev user for local development."""
from app.db.session import SessionLocal
from app.db.models import User

db = SessionLocal()

try:
    # Check if dev user already exists
    existing = db.query(User).filter(User.auth0_id == 'dev-user-1').first()

    if not existing:
        # Create dev user
        user = User(
            auth0_id='dev-user-1',
            email='dev@local.com',
            name='Dev User'
        )
        db.add(user)
        db.commit()
        print('Dev user created successfully')
    else:
        print('Dev user already exists')
finally:
    db.close()
