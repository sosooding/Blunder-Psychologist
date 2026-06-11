FROM node:20-slim

WORKDIR /app

# Install deps first for layer caching (no lockfile yet — Phase 0 scaffold).
COPY web/package.json /app/package.json
RUN npm install

COPY web/ /app/

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
