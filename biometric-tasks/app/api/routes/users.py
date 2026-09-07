from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db, verify_admin
from app.schemas.schemas import UserEnrollRequest, UserDeleteRequest
from app.services.user_service import enroll_user, delete_user
from app.models.domain import AdminUser, RoleEnum

router = APIRouter()

@router.post("/enroll")
async def register_user(
    data: UserEnrollRequest,
    admin: AdminUser = Depends(verify_admin),
    db: AsyncSession = Depends(get_db)
):
    # Default to the logged-in admin's tenant ID
    target_tenant_id = admin.tenant_id
    
    # If Super Admin, override with the target provided in the payload
    if admin.role == RoleEnum.SUPER_ADMIN:
        if not data.target_tenant_id:
            raise HTTPException(status_code=400, detail="Super Admins must specify a target_tenant_id")
        target_tenant_id = data.target_tenant_id
    elif not target_tenant_id:
        raise HTTPException(status_code=403, detail="Tenant Admin is not assigned to an organization")

    user = await enroll_user(target_tenant_id, data.finger_id, data.name, db)
    return {"status": "success", "message": "User enrolled locally. Fire MQTT command to sync hardware."}

@router.post("/delete")
async def remove_user(
    data: UserDeleteRequest,
    admin: AdminUser = Depends(verify_admin),
    db: AsyncSession = Depends(get_db)
):
    # Default to the logged-in admin's tenant ID
    target_tenant_id = admin.tenant_id
    
    # If Super Admin, override with the target provided in the payload
    if admin.role == RoleEnum.SUPER_ADMIN:
        if not data.target_tenant_id:
            raise HTTPException(status_code=400, detail="Super Admins must specify a target_tenant_id")
        target_tenant_id = data.target_tenant_id
    elif not target_tenant_id:
        raise HTTPException(status_code=403, detail="Tenant Admin is not assigned to an organization")

    await delete_user(target_tenant_id, data.finger_id, db)
    return {"status": "success", "message": "User deleted locally. Fire MQTT command to sync hardware."}