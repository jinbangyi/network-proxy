# Development tasks

## external context

- `v2ray-docker-compose` abs path: /home/king/github/jinbangyi/v2ray-docker-compose
- `network-proxy` abs path: /home/king/github/jinbangyi/network-proxy

## tasks

- [ ] feat/init: http proxy service
  **task description**:
  - user get subscription links: user -> server <- [client1, client2, ...]
  - admin user add client: admin -> client -auto-> server
  - pool health: server -check-> client, server -reconfigure-> client

  **expected outcome**:
  - the admin can use docker easy start a proxy client, and the client will automatically add to the proxy pool
  - the admin will give user several subscription links for different client, for example clash, v2rayN, flclash, etc.
  - the server will auto reconfigure the client when the client is reachable but that port is not working (china -> server in china -> client in japan, the port is blocked in china but not in japan, so the server should try to increase the port number of that client and update the subscription links)
  - the connection between server and client should be bidirectional, the proxy channel is not only (user -> client) which user will connect to client's port directly(maybe blocked, server should health check and reconfigure), but also (user -> server -> client) which the client will connect to the server's port to create the proxy channel

  **task context**:
  - use v2ray core as proxy server
  - use subconverter to support multi protocols
  - use subscribe.py to expose a subscribe link for users
  - client should be easy to join the proxy pool, for example, input the server link and wait the server to approve the request and join to the proxy pool
  - server should be able to manage the proxy pool, for example, approve or reject the join request, remove the user from the proxy pool, etc.
  - server has health check mechanism to monitor the status of the proxy pool, and if one of the proxy server is not reachable, the server should try to increase the port number of that proxy and update the proxy pool accordingly, and if the proxy server is still not reachable after several attempts, the server should remove that proxy from the proxy pool
