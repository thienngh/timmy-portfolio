import serial
import matplotlib.pyplot as plt
import time
import math

PORT = '/dev/cu.usbmodem101'
BAUD = 115200
VREF = 5.0
SENSITIVITY = 0.0025   # V/kPa
GAIN = 1000            # Rg = 3 ohm -> gain ~ 2001
FS = 100.0
DT = 1.0 / FS
SECONDS = 6

# Venturi geometry
d2 = 8e-3
d1 = 26e-3
A2 = math.pi * (d2 / 2)**2
A1 = math.pi * (d1 / 2)**2
rho = 1.225

ser = serial.Serial(PORT, BAUD, timeout=0.2)
time.sleep(2)
ser.reset_input_buffer()

print("Triggering Arduino and waiting for breathing...")
ser.write(b's')

times = []
voltages = []
pressures_kpa = []
flows_m3s = []
flows_Ls = []

baseline_voltages = []
baseline_flows = []
baseline_voltage = 0.0
flow_threshold = 0.35

recording_started = False
recording_finished = False
breathing_started = False
breath_start_time = None
last_plot = 0.0

plt.ion()

# Figure 1: Voltage
fig1, ax1 = plt.subplots(figsize=(10, 4))
line_v, = ax1.plot([], [], 'b-')
ax1.set_xlabel("Time (s)")
ax1.set_ylabel("Voltage (V)")
ax1.grid(True)
ax1.set_title("Voltage")

# Figure 2: Pressure
fig2, ax2 = plt.subplots(figsize=(10, 4))
line_p, = ax2.plot([], [], 'r-')
ax2.set_xlabel("Time (s)")
ax2.set_ylabel("Pressure Difference (kPa)")
ax2.grid(True)
ax2.set_title("Pressure")

# Figure 3: Flow
fig3, ax3 = plt.subplots(figsize=(10, 4))
line_q, = ax3.plot([], [], 'g-')
ax3.set_xlabel("Time (s)")
ax3.set_ylabel("Flow Rate (L/s)")
ax3.grid(True)
ax3.set_title("Flow Rate")

try:
    overall_start = time.time()

    while True:
        if time.time() - overall_start > 30:
            print("Timed out waiting for acquisition to finish.")
            break

        raw = ser.readline().decode(errors='ignore').strip()
        if not raw:
            continue

        if raw.startswith("B,"):
            try:
                adc = float(raw.split(",")[1])
            except (ValueError, IndexError):
                continue
            baseline_voltages.append(adc * VREF / 1023.0)
            continue

        if raw == "START":
            if not baseline_voltages:
                print("No baseline samples received.")
                break

            baseline_voltage = sum(baseline_voltages) / len(baseline_voltages)

            for v in baseline_voltages:
                dv = v - baseline_voltage
                pkpa = dv / SENSITIVITY / GAIN
                ppa = pkpa * 1000.0

                if ppa == 0:
                    q_ls = 0.0
                else:
                    q_mag = A2 * math.sqrt(
                        (2.0 * abs(ppa)) /
                        (rho * (1.0 - (A2 / A1) ** 2))
                    )
                    q_ls = q_mag * 1000.0

                baseline_flows.append(abs(q_ls))

            max_baseline_flow = max(baseline_flows) if baseline_flows else 0.0
            flow_threshold = max(0.05, 1.2 * max_baseline_flow)

            print("Baseline voltage:", baseline_voltage, "V")
            print("Baseline max flow:", max_baseline_flow, "L/s")
            print("Using threshold:", flow_threshold, "L/s")

            recording_started = True
            continue

        if raw == "END":
            recording_finished = True
            break

        if not recording_started:
            continue

        try:
            adc = float(raw)
        except ValueError:
            continue

        voltage = adc * VREF / 1023.0
        delta_voltage = max(voltage - baseline_voltage, 0.0)
        pressure_kpa = delta_voltage / SENSITIVITY / GAIN
        pressure_pa = pressure_kpa * 1000.0

        if pressure_pa == 0:
            flow_m3s = 0.0
        else:
            flow_mag = A2 * math.sqrt(
                (2.0 * abs(pressure_pa)) /
                (rho * (1.0 - (A2 / A1) ** 2))
            )
            flow_m3s = math.copysign(flow_mag, pressure_pa)

        flow_ls = flow_m3s * 1000.0

        if not breathing_started:
            if abs(flow_ls) > flow_threshold:
                breathing_started = True
                breath_start_time = time.time()
            else:
                continue

        t = time.time() - breath_start_time
        if t > SECONDS:
            break

        times.append(t)
        voltages.append(voltage)
        pressures_kpa.append(pressure_kpa)
        flows_m3s.append(flow_m3s)
        flows_Ls.append(flow_ls)

        if t - last_plot > 0.05:
            line_v.set_xdata(times)
            line_v.set_ydata(voltages)

            line_p.set_xdata(times)
            line_p.set_ydata(pressures_kpa)

            line_q.set_xdata(times)
            line_q.set_ydata(flows_Ls)

            ax1.relim()
            ax1.autoscale_view(scaley=True)

            ax2.relim()
            ax2.autoscale_view(scaley=True)

            ax3.relim()
            ax3.autoscale_view(scaley=True)

            plt.pause(0.001)
            last_plot = t

    fev1 = 0.0
    fvc = 0.0

    if not recording_finished:
        print("Warning: did not receive END marker from Arduino.")

    if len(flows_Ls) == 0:
        print("No flow samples collected.")
    else:
        start_idx = 0
        end_idx = len(flows_Ls)
        below_count = 0

        for i in range(start_idx, len(flows_Ls)):
            aq = abs(flows_Ls[i])

            if aq > flow_threshold:
                below_count = 0
            else:
                below_count += 1
                if below_count >= 20:
                    end_idx = max(start_idx + 1, i - 19)
                    break

        fev1_end = min(start_idx + int(FS * 1.0), end_idx)

        if fev1_end > start_idx:
            fev1 = sum(abs(flows_Ls[i]) * DT for i in range(start_idx, fev1_end))

        if end_idx > start_idx:
            fvc = sum(abs(flows_Ls[i]) * DT for i in range(start_idx, end_idx))

        print("start_idx:", start_idx, "end_idx:", end_idx, "duration_s:", (end_idx - start_idx) * DT)

    print("FEV1:", fev1, "L")
    print("FVC:", fvc, "L")

    result_line = f"R,{fev1:.2f},{fvc:.2f}\n"
    print("Sending to Arduino LCD:", result_line.strip())
    ser.write(result_line.encode())
    ser.flush()
    time.sleep(0.5)

finally:
    ser.close()
    plt.ioff()
    plt.show()

if voltages:
    print("Min voltage:", min(voltages), "V")
    print("Max voltage:", max(voltages), "V")
    print("Peak-to-peak voltage:", max(voltages) - min(voltages), "V")
    print("Min pressure:", min(pressures_kpa), "kPa")
    print("Max pressure:", max(pressures_kpa), "kPa")
    print("Min flow:", min(flows_Ls), "L/s")
    print("Max flow:", max(flows_Ls), "L/s")
else:
    print("No data received.")
