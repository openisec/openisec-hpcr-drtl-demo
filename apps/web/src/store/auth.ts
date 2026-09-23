import { create } from "zustand";

interface Membership {
  organization_id: string;
  organization_name: string;
  role: string;
}

interface User {
  id: string;
  email: string;
  full_name: string;
  is_platform_admin: boolean;
  must_change_password: boolean;
  memberships: Membership[];
  active_org_id: string | null;
}

interface AuthStore {
  user: User | null;
  mustChangePassword: boolean;
  hydrated: boolean;
  setUser: (user: User) => void;
  clearAuth: () => void;
  setMustChangePassword: (value: boolean) => void;
  setHydrated: (value: boolean) => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  mustChangePassword: false,
  hydrated: false,
  setUser: (user) =>
    set({
      user,
      mustChangePassword: user.must_change_password,
    }),
  clearAuth: () => {
    set({ user: null, mustChangePassword: false });
  },
  setMustChangePassword: (value) => set({ mustChangePassword: value }),
  setHydrated: (value) => set({ hydrated: value }),
}));