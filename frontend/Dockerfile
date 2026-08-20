# Stage 1: development (deps only, source bind-mounted by docker-compose.dev.yml)
FROM node:20-alpine AS development
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Stage 2: build
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Vite inlines VITE_* vars at build time, so the API URL has to be baked in
# here — setting it on the running container does nothing. Defaults to empty,
# meaning the SPA calls its own origin (/api/v1/...), which is what Caddy
# serves in production. Without this ARG the production bundle would ship
# src/services/api.ts's dev fallback of http://localhost:8000.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 3: serve (production)
FROM nginx:alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
