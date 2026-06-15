- [ ] @tests/test.sh the proxy seems not work, you should use a client to test the proxy is work or not
  - 'http://127.0.0.1:9001/subscribe/clash?token=sub-db' why 500
  - why the 'node-v2ray-1' seems in restart loop
  - why `export https_proxy=http://localhost:10808 && curl https://ifconfig.me` not work?
  - when i restart agent, how server know the restarted agent is still the same agent? or it will full update all info related to the agent from report?

- [ ] the subscription should include directly proxy and relay proxy. the relay should node start connection to manager, not manager to node.
