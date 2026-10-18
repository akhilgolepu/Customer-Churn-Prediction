FROM node:22-alpine AS build

WORKDIR /app/frontend

COPY package*.json ./
RUN npm ci

COPY . ./
# Build-time API URL (Vite inlines it). Passed explicitly so the image does not
# depend on a committed frontend/.env.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]