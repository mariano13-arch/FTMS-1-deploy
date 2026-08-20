# FTMS Driver Mobile

Expo/React Native foundation for the driver trip-execution companion app. Driver authentication uses the existing Django session and CSRF endpoints. Assignments, trip actions, location, maps, and persistence are not implemented.

## Configure the backend base URL

Copy `.env.example` to a local `.env.local` and set `EXPO_PUBLIC_API_BASE_URL` to the Django server origin reachable from the phone or emulator. Do not put credentials, tokens, or API keys in this variable.

The app bootstraps a CSRF token and uses Django's session cookie through the platform network layer. Passwords, session-cookie values, and CSRF tokens are not persisted in AsyncStorage.

New Driver accounts receive a temporary setup link. The app accepts the link at `ftms-driver://setup-password`, sends the setup token to Django, and returns the Driver to explicit sign-in after the password is created.

For local device testing, configure the existing Django environment variables as needed:

- `DJANGO_ALLOWED_HOSTS` must include the backend host name or address used by the device.
- `DJANGO_CORS_ALLOWED_ORIGINS` and `DJANGO_CSRF_TRUSTED_ORIGINS` must include the actual development origin when the client supplies one.
- `DJANGO_SESSION_COOKIE_SECURE=false` and `DJANGO_CSRF_COOKIE_SECURE=false` may be used only for deliberate local HTTP development. Keep secure cookies enabled outside local development.

Driver onboarding email uses these optional backend environment settings:

- `DRIVER_MOBILE_ACCOUNT_SETUP_URL`
- `DRIVER_MOBILE_APP_DOWNLOAD_URL`
- `DJANGO_EMAIL_BACKEND`
- `DJANGO_EMAIL_HOST`
- `DJANGO_EMAIL_PORT`
- `DJANGO_EMAIL_HOST_USER`
- `DJANGO_EMAIL_HOST_PASSWORD`
- `DJANGO_EMAIL_USE_TLS`
- `DJANGO_DEFAULT_FROM_EMAIL`

The default local email backend writes the invitation to the backend console. To deliver invitations through Gmail, put the following values in the repository root `.env` only; never commit the file or share the app password:

```dotenv
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DJANGO_EMAIL_HOST=smtp.gmail.com
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_HOST_USER=your-gmail-address
DJANGO_EMAIL_HOST_PASSWORD=your-google-app-password
DJANGO_EMAIL_USE_TLS=true
DJANGO_DEFAULT_FROM_EMAIL=your-gmail-address
DRIVER_MOBILE_ACCOUNT_SETUP_URL=http://localhost:5173/setup-password
```

Use a Google App Password rather than the normal Gmail password. The Google account must have 2-Step Verification enabled before an App Password can be created. The FTMS web URL above can be replaced with `ftms-driver://setup-password` when invitations should open the installed native development build. `DRIVER_MOBILE_APP_DOWNLOAD_URL` remains blank until an installable application is distributed.

## Install and start

```bash
cd mobile
npm install
npm start
```

The custom `ftms-driver://` setup link requires the FTMS Android development build. For the first native install, enable USB debugging, connect the Android phone, and run:

```bash
npm run android:device
```

After the build is installed, normal JavaScript/TypeScript development only needs:

```bash
npm run start:dev-client
```

Keep the phone and development computer on the same network, open the installed FTMS Driver development build, and connect it to the development server. Rebuild with `npm run android:device` whenever native dependencies or app configuration change.

For an Android emulator with Android Studio configured, create/install the development build with:

```bash
npx expo run:android
```

## Quality checks

```bash
npm run typecheck
npm run validate
```
