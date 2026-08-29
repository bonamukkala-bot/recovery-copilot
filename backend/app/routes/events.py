from fastapi import APIRouter
from app.services.supabase_client import supabase

router = APIRouter()


@router.get("/events")
def get_events():
    result = (
        supabase.table("events")
        .select("*")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return result.data