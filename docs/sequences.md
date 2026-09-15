# Button-triggered joint sequences

The normal `planetj` process publishes PLNJ independently of a joint-sequence
worker. Pressing a configured chord starts one sequence. Network waits and
interpolation happen in the worker; the input loop only observes button edges
and cancellation. No subprocess is started for each button press.

```bash
./scripts/run.sh --config configs/entry/entry_sequences.yaml
```

The supplied file demonstrates two joints and a receiver state named
`upper_stream` (ID 5). Use a task entry for a real robot. IDs belong to the
receiving registry and are not globally assigned by PlanetJoystick.

```yaml
extends: ../operator.yaml
inputs:
  requests:
    upper_stream: {buttons: [4, 2], blocked_by: [5], request_id: 5}
sequences:
  target: {host: 127.0.0.1, port: 15100}
  publisher: {hz: 60, status_hz: 10, timeout_s: 0.03}
  cancel: {buttons: [4, 1], blocked_by: [5]}
  motions:
    example:
      buttons: [4, 3]
      blocked_by: [5]
      state: {id: 5, key: upper_stream}
      trajectory: ../../data/sequences/two_joint.npz
      entry_duration_s: 2.0
      playback_speed: 1.0
```

This example overlay belongs in `configs/entry/`. Paths resolve relative to
the YAML declaring `trajectory`, even through inherited configuration. A task
can override one motion or set a motion to `null` while keeping others; set
`sequences: null` to disable the worker. The configured PLNJ `target` and the
joint-target `sequences.target` are separate destinations.

## File and receiver contract

NPZ files are loaded with `allow_pickle=False` before input starts:

| Field | Meaning |
| --- | --- |
| `time_s` | Strictly increasing seconds starting at zero |
| `joint_pos` | Frame-by-joint absolute position targets, radians |
| `joint_names` | Unique names identifying trajectory columns |

Extra arrays are ignored. There are no IK, policy, PD or robot-specific imports.
The generic implementation depends on NumPy and Planet configuration/protocol
packages. Model files and task motion data belong to the consuming repository.

The worker queries `planet.joint-target.v1` status. It requires a live
`activation`, matching `state_id`/`state_key`, matching `joint_names`, current
committed `q_des`, and the latest received `sequence`. It maps columns by name,
then blends from that committed target to the first frame with smoothstep.
Playback uses elapsed time and linear interpolation, independent of source
frame rate. The receiver owns joint limits and command execution.

The producer does not automatically enter a state or wait indefinitely for it
to become active. Enter the stream state, then press the play chord. Missing
ownership/joint metadata or an inactive endpoint reports an error and sends
no sequence. Older protocol clients still work; sequence playback needs the
receiver's extended status metadata.

## Trigger, cancellation and holding

- A fresh press starts one clip; releasing the button lets it continue.
- A held button at connection/reconnection does not start playback.
- Presses during playback are ignored rather than queued.
- The cancel chord, any safety signal, a request for another state, physical
  disconnection, or a changed receiver activation stops that playback.
- Cancellation sends no replacement posture. The receiver keeps its latest
  target according to its normal state and safety rules.
- The final frame is retried with increasing sequence numbers until received;
  the worker then reports `HOLD` and stops sending. That receipt does not mean
  the robot has physically reached the pose.
- Another fresh press can play again within the same activation. Its sequence
  numbers continue above the receiver's latest value and its entry blend starts
  from the current committed target.

On a lost reply, the worker discards the old socket, checks the activation again,
and sends the sample for the current time. It never queues old frames or carries
a clip into a new activation. A delayed exchange stays outside the PLNJ loop.
Only one upper-target producer should control an endpoint at a time; independent
operator status queries can coexist.
