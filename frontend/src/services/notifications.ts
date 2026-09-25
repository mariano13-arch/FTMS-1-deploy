import { api } from "./api";

export type UserNotification = {
  id: number;
  notification_type: string;
  title: string;
  message: string;
  target_url: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
};

export type NotificationPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: UserNotification[];
};

export const getNotifications = () =>
  api<NotificationPage>("/api/v1/auth/notifications/?page_size=20");

export const getUnreadNotificationCount = () =>
  api<{ unread_count: number }>("/api/v1/auth/notifications/unread-count/");

export const markNotificationRead = (notificationId: number) =>
  api<UserNotification>(`/api/v1/auth/notifications/${notificationId}/read/`, {
    method: "POST",
  });

export const markAllNotificationsRead = () =>
  api<{ updated: number }>("/api/v1/auth/notifications/mark-all-read/", {
    method: "POST",
  });
