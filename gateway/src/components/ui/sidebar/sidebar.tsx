"use client"

// ─── Sidebar shell — re-exports everything from sub-modules ──────────
// Import paths remain `@/components/ui/sidebar` for all consumers.

export {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInput,
  SidebarInset,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from "./_sidebar_footer"

export {
  sidebarMenuButtonVariants,
} from "./_sidebar_content"

export type { SidebarContextProps } from "./types"
