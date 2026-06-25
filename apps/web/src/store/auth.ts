import { create } from "zustand";
import { setToken } from "@/lib/api";

interface User {
  user_id: string;
  email: string;
  full_name: string;
  organization_id: string;
}

interface AuthStore {
  user: User | null;
  setUser: (user: User | null) => void;
  setAuth: (user: User, token: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  setUser: (user) => set({ user }),
  setAuth: (user, token) => {
    setToken(token);
    set({ user });
  },
  clearAuth: () => {
    setToken(null);
    set({ user: null });
  },
}));