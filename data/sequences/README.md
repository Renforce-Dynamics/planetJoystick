# Example joint sequence

`two_joint.npz` contains a one-second position sequence in radians for
`joint_a` and `joint_b`. It illustrates the file contract and is not a robot
asset. Configure the receiver's state ID/key and use a trajectory whose joint
names match its upper joint partition before starting playback.

Only `time_s`, `joint_pos` and `joint_names` are required. Extra arrays are not
sent. Names define identity; the producer maps columns into the receiver's
advertised order. Trajectories remain outside the Python package.
