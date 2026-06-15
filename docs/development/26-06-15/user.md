- [x] @tests/test.sh the proxy seems not work, you should use a client to test the proxy is work or not
  - 'http://127.0.0.1:9001/subscribe/clash?token=sub-db' why 500
  - why the 'node-v2ray-1' seems in restart loop
  - why `export https_proxy=http://localhost:10808 && curl https://ifconfig.me` not work?
  - when i restart agent, how server know the restarted agent is still the same agent? or it will full update all info related to the agent from report?

- [x] should create a simple dashboard, admin can easy approve the join request and see all the nodes info

- [x] github ci, build docker and upload to dockerhub registry
- [x] add k8s deployment yaml
- [x] create a onboard script in scripts/, so that user can use the script to easy start the manager and node
  - default workspace: /opt/network-proxy
  - default database: sqlite, stored in workspace/data/network_proxy.db


