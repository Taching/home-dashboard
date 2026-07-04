# Remote phone access with Tailscale

This deployment keeps the dashboard private. Docker continues to bind the UI
to `127.0.0.1:8080`; Tailscale Serve provides the only remote entry point and
allows only devices permitted by the Tailscale account's access policy.

Do not use router port forwarding or Tailscale Funnel for this dashboard.
Funnel makes a service available to the public internet, while Serve limits it
to the private tailnet.

## One-time Pi setup

1. Install Tailscale using the [official Linux installation instructions](https://tailscale.com/docs/install/linux).
2. Join the Pi to the Tailscale account:

   ```sh
   sudo tailscale up
   ```

   Follow the URL printed by the command to authorize the Pi.
3. From the project root, install and start the dashboard proxy:

   ```sh
   ./deploy/setup-tailscale-serve.sh
   ```

   The first HTTPS setup can require a one-time approval in Tailscale. Follow
   any URL printed by the command.

## Phone access

1. Install the Tailscale iOS or Android app and sign in with the same account.
2. On the Pi, run:

   ```sh
   tailscale serve status
   ```

3. Open the displayed `https://<device>.<tailnet>.ts.net` URL on the phone.

The Serve configuration uses `--bg`, so Tailscale restores it after a reboot.
The accompanying systemd unit reapplies the configuration when Tailscale starts.

## Operations

```sh
sudo systemctl status chili-tailscale-serve
tailscale serve status
sudo systemctl disable --now chili-tailscale-serve
```
