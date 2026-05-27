FROM node:20-slim

WORKDIR /app

# Deps first for layer caching.
COPY package.json ./
RUN npm install

# App source + production build.
COPY . .
RUN npm run build

EXPOSE 3100
# Overridden to `npm run worker` by the worker compose service.
CMD ["npm", "run", "start"]
