from pydantic import BaseModel, EmailStr, field_validator, model_validator
import re


def validate_password_complexity(v: str) -> str:
    if len(v) < 12:
        raise ValueError("パスワードは12文字以上で入力してください")
    if not re.search(r"[A-Z]", v):
        raise ValueError("パスワードには大文字を含めてください")
    if not re.search(r"[a-z]", v):
        raise ValueError("パスワードには小文字を含めてください")
    if not re.search(r"\d", v):
        raise ValueError("パスワードには数字を含めてください")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
        raise ValueError("パスワードには記号を含めてください")
    return v


def validate_name_no_space(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("氏名を入力してください")
    if " " in v or "\u3000" in v:  # 半角スペース・全角スペース禁止
        raise ValueError("姓・名にはスペースを含めないでください")
    return v


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    password_confirm: str
    family_name: str
    given_name: str
    organization_name: str
    agree_terms: bool
    agree_privacy: bool
    marketing_opt_in: bool = False
    token: str

    @field_validator("agree_terms")
    @classmethod
    def must_agree_terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError("利用上の注意・免責事項への同意が必要です")
        return v

    @field_validator("agree_privacy")
    @classmethod
    def must_agree_privacy(cls, v: bool) -> bool:
        if not v:
            raise ValueError("プライバシーポリシーへの同意が必要です")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_complexity(v)

    @field_validator("family_name", "given_name")
    @classmethod
    def name_no_space(cls, v: str) -> str:
        return validate_name_no_space(v)

    @field_validator("family_name", "given_name", "organization_name")
    @classmethod
    def no_script(cls, v: str) -> str:
        if "<" in v or ">" in v:
            raise ValueError("使用できない文字が含まれています")
        return v.strip()

    @model_validator(mode="after")
    def validate_passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("パスワードと確認用パスワードが一致しません")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    organization_id: str
    message: str = "OK"


class MembershipInfo(BaseModel):
    organization_id: str
    organization_name: str
    role: str


class LoginResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    organization_id: str
    is_platform_admin: bool
    memberships: list[MembershipInfo]
    message: str = "ログインしました"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_complexity(v)


class MessageResponse(BaseModel):
    message: str


class SwitchOrgRequest(BaseModel):
    organization_id: str
    password: str


class SwitchOrgResponse(BaseModel):
    organization_id: str
    organization_name: str
    role: str
    message: str = "組織を切り替えました"


class MeResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    organization_id: str
    active_organization_id: str
    is_platform_admin: bool


class MemberCreateRequest(BaseModel):
    email: EmailStr
    family_name: str
    given_name: str
    role: str = "member"
    organization_id: str | None = None

    @field_validator("family_name", "given_name")
    @classmethod
    def name_no_space(cls, v: str) -> str:
        return validate_name_no_space(v)

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        allowed = {"owner", "admin", "approver", "member"}
        if v not in allowed:
            raise ValueError(f"role must be one of {sorted(allowed)}")
        return v

class MemberCreateResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    organization_id: str
    temp_password: str | None = None
    message: str = "メンバーを作成しました"


class UserMeResponse(BaseModel):
    id: str
    email: str
    full_name: str
    is_platform_admin: bool
    must_change_password: bool
    memberships: list[MembershipInfo]
    active_org_id: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_complexity(v)

    @model_validator(mode="after")
    def validate_passwords_match(self):
        if self.new_password != self.new_password_confirm:
            raise ValueError("新しいパスワードと確認用パスワードが一致しません")
        if self.new_password == self.current_password:
            raise ValueError("現在のパスワードと同じパスワードは使用できません")
        return self


class PasswordChangeResponse(BaseModel):
    message: str = "パスワードを変更しました"


class MemberListItem(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    organization_id: str
    organization_name: str
    must_change_password: bool
    is_active: bool
    created_at: str
    # このユーザー自身の個人組織のID(存在する場合)。フロントエンドが
    # 組織変更プルダウンから「他人の個人組織」を除外するために使用する。
    personal_org_id: str | None = None


class MemberListResponse(BaseModel):
    members: list[MemberListItem]


class MemberUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    new_organization_id: str | None = None

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"owner", "admin", "approver", "member"}
        if v not in allowed:
            raise ValueError(f"role must be one of {sorted(allowed)}")
        return v


class MemberUpdateResponse(BaseModel):
    user_id: str
    role: str
    is_active: bool
    message: str = "メンバー情報を更新しました"


class ReissueTempPasswordResponse(BaseModel):
    user_id: str
    temp_password: str
    message: str = "一時パスワードを再発行しました"
    
    
class OrganizationListItem(BaseModel):
    id: str
    name: str
    is_active: bool = True
    risk_score_threshold: int = 70
    is_personal: bool = False


class OrganizationListResponse(BaseModel):
    organizations: list[OrganizationListItem]


class OrganizationUpdateRequest(BaseModel):
    """
    E. 「管理設定」からの組織更新。
    - risk_score_threshold: 組織admin(自組織のみ)/Platform admin(全組織)が変更可
    - name / is_active: Platform adminのみ変更可(エンドポイント側で権限判定)
    """
    name: str | None = None
    is_active: bool | None = None
    risk_score_threshold: int | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("組織名を入力してください")
        if "<" in v or ">" in v:
            raise ValueError("使用できない文字が含まれています")
        return v

    @field_validator("risk_score_threshold")
    @classmethod
    def threshold_in_range(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < 0 or v > 100:
            raise ValueError("リスクスコア閾値は0〜100の範囲で入力してください")
        return v


class OrganizationUpdateResponse(BaseModel):
    id: str
    name: str
    is_active: bool
    risk_score_threshold: int
    message: str = "組織情報を更新しました"


class NameUpdateRequest(BaseModel):
    """
    C. 個人アカウントページ: 自分自身の氏名変更。
    登録・メンバー作成と同じルール(スペース禁止)を適用する。
    """
    family_name: str
    given_name: str

    @field_validator("family_name", "given_name")
    @classmethod
    def name_no_space(cls, v: str) -> str:
        return validate_name_no_space(v)

    @field_validator("family_name", "given_name")
    @classmethod
    def no_script(cls, v: str) -> str:
        if "<" in v or ">" in v:
            raise ValueError("使用できない文字が含まれています")
        return v.strip()


class NameUpdateResponse(BaseModel):
    full_name: str
    message: str = "氏名を変更しました"


class OrganizationCreateRequest(BaseModel):
    """
    G(仮). Platform adminによる組織の箱だけの作成。
    メンバーは後から /auth/members で追加する想定。
    """
    name: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("組織名を入力してください")
        if "<" in v or ">" in v:
            raise ValueError("使用できない文字が含まれています")
        return v


class OrganizationCreateResponse(BaseModel):
    id: str
    name: str
    message: str = "組織を作成しました"

class PreRegisterRequest(BaseModel):
    email: EmailStr


class VerifyEmailResponse(BaseModel):
    email: str
    message: str = "\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u306e\u78ba\u8a8d\u304c\u5b8c\u4e86\u3057\u307e\u3057\u305f"
