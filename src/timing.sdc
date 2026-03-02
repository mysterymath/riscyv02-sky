# Custom SDC for TT mux/demux bus protocol (negedge-sensitive CPU).
#
# Based on librelane base.sdc with corrected output constraints:
# the TT bus protocol multiplexes address and data on the same pins,
# alternating every half-cycle. Address is sampled at posedge, data at
# negedge. The default base.sdc constrains all outputs to posedge only,
# over-constraining data paths and under-constraining nothing.
#
# This SDC adds a virtual clock (clk_data) aligned to the negedge, then
# uses set_false_path -through the pinned AB/DO nets to ensure each path
# is checked against the correct sampling edge only.
#
# Requires (* keep *) on the AB and DO wires in project.v so that
# the net names survive synthesis.

# -----------------------------------------------------------------------
# Clock
# -----------------------------------------------------------------------
set clock_port __VIRTUAL_CLK__
if { [info exists ::env(CLOCK_PORT)] } {
    set port_count [llength $::env(CLOCK_PORT)]

    if { $port_count == "0" } {
        puts "\[WARNING] No CLOCK_PORT found. A dummy clock will be used."
    } elseif { $port_count != "1" } {
        puts "\[WARNING] Multi-clock files are not currently supported by the base SDC file. Only the first clock will be constrained."
    }

    if { $port_count > "0" } {
        set ::clock_port [lindex $::env(CLOCK_PORT) 0]
    }
}
set port_args [get_ports $clock_port]
puts "\[INFO] Using clock $clock_port…"
create_clock {*}$port_args -name $clock_port -period $::env(CLOCK_PERIOD)

# Virtual clock aligned to negedge — for data-phase output constraints.
set half_period [expr $::env(CLOCK_PERIOD) / 2.0]
create_clock -name clk_data -period $::env(CLOCK_PERIOD) \
    -waveform [list $half_period $::env(CLOCK_PERIOD)]

# -----------------------------------------------------------------------
# I/O delays
# -----------------------------------------------------------------------
set input_delay_value [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]
# Output delay models the TT mux round-trip: clk pad → tt_ctrl → tt_mux →
# project pin → [project logic] → project pin → tt_mux → tt_ctrl → IO pad.
# The input path (pad → project) adds ~5.7ns to the clock arrival; the output
# path (project → pad) adds ~16.5ns to data arrival.  Total round-trip
# penalty on output setup: ~22ns.  Any remaining slack is available as
# board-level setup margin for external latches/SRAM.
set output_delay_value 22
puts "\[INFO] Setting output delay to: $output_delay_value"
puts "\[INFO] Setting input delay to: $input_delay_value"

# -----------------------------------------------------------------------
# Design constraints
# -----------------------------------------------------------------------
set_max_fanout $::env(MAX_FANOUT_CONSTRAINT) [current_design]
if { [info exists ::env(MAX_TRANSITION_CONSTRAINT)] } {
    set_max_transition $::env(MAX_TRANSITION_CONSTRAINT) [current_design]
}
if { [info exists ::env(MAX_CAPACITANCE_CONSTRAINT)] } {
    set_max_capacitance $::env(MAX_CAPACITANCE_CONSTRAINT) [current_design]
}

# -----------------------------------------------------------------------
# Input delays (same as base.sdc)
# -----------------------------------------------------------------------
set clk_input [get_port $clock_port]
set clk_indx [lsearch [all_inputs] $clk_input]
set all_inputs_wo_clk [lreplace [all_inputs] $clk_indx $clk_indx ""]
set all_inputs_wo_clk_rst $all_inputs_wo_clk

set clocks [get_clocks $clock_port]

set_input_delay $input_delay_value -clock $clocks $all_inputs_wo_clk_rst

# Control inputs (IRQB, NMIB, RDY, SOB): driven by bus peripherals on
# negedge.  Both CPUs capture at negedge → negedge-to-negedge
# (full-period) setup relationship.
set_input_delay $input_delay_value -clock $clocks -clock_fall \
    [get_ports {ui_in[0] ui_in[1] ui_in[2] ui_in[3] \
                ui_in[4] ui_in[5] ui_in[6] ui_in[7]}]

# -----------------------------------------------------------------------
# Output delays — dual-edge constraints for muxed bus
# -----------------------------------------------------------------------
# Output hold: the TT mux provides >11ns of board-level hold (mux_clk_in_min
# + CK→Q_fast + mux_out_min ≈ 3 + 0.3 + 8 = 11.3ns), far exceeding any
# external latch requirement.  No project-pin hold constraint needed.
set output_hold_value 0

# Setup (max) — posedge constraint on all outputs (address phase).
set_output_delay -max $output_delay_value -clock $clocks [all_outputs]
# Hold (min) — no project-pin hold requirement (mux provides board-level hold).
set_output_delay -min $output_hold_value -clock $clocks [all_outputs]

# Setup (max) — negedge constraint on muxed bus outputs (data phase).
set_output_delay -max $output_delay_value -clock clk_data -add_delay \
    [get_ports {uio_out[0] uio_out[1] uio_out[2] uio_out[3] \
                uio_out[4] uio_out[5] uio_out[6] uio_out[7] \
                uo_out[0] uo_out[1] uo_out[2] uo_out[3] \
                uo_out[4] uo_out[5] uo_out[6] uo_out[7] \
                uio_oe[0] uio_oe[1] uio_oe[2] uio_oe[3] \
                uio_oe[4] uio_oe[5] uio_oe[6] uio_oe[7]}]
# Hold (min) — no project-pin hold requirement (mux provides board-level hold).
set_output_delay -min $output_hold_value -clock clk_data -add_delay \
    [get_ports {uio_out[0] uio_out[1] uio_out[2] uio_out[3] \
                uio_out[4] uio_out[5] uio_out[6] uio_out[7] \
                uo_out[0] uo_out[1] uo_out[2] uo_out[3] \
                uo_out[4] uo_out[5] uo_out[6] uo_out[7] \
                uio_oe[0] uio_oe[1] uio_oe[2] uio_oe[3] \
                uio_oe[4] uio_oe[5] uio_oe[6] uio_oe[7]}]

# -----------------------------------------------------------------------
# False paths — exclude incorrect sampling edge for each bus phase
# -----------------------------------------------------------------------
# Data-phase nets (DO, RWB, SYNC) are only valid during data phase
# (sampled at negedge). Kill the posedge check for paths through them.
set_false_path -through [get_nets {DO[0] DO[1] DO[2] DO[3] \
                                   DO[4] DO[5] DO[6] DO[7]}] \
               -to [get_clocks $clock_port]

set_false_path -through [get_nets {RWB}] -to [get_clocks $clock_port]

set_false_path -through [get_nets {SYNC}] -to [get_clocks $clock_port]

# Address nets (AB) are only valid during address phase (sampled at posedge).
# Kill the negedge check for paths through AB.
set_false_path -through [get_nets {AB[0] AB[1] AB[2] AB[3] \
                                   AB[4] AB[5] AB[6] AB[7] \
                                   AB[8] AB[9] AB[10] AB[11] \
                                   AB[12] AB[13] AB[14] AB[15]}] \
               -to [get_clocks clk_data]

# -----------------------------------------------------------------------
# Driving cells
# -----------------------------------------------------------------------
if { ![info exists ::env(SYNTH_CLK_DRIVING_CELL)] } {
    set ::env(SYNTH_CLK_DRIVING_CELL) $::env(SYNTH_DRIVING_CELL)
}

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 1] \
    $all_inputs_wo_clk_rst

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 1] \
    $clk_input

# -----------------------------------------------------------------------
# Output load
# -----------------------------------------------------------------------
set cap_load [expr $::env(OUTPUT_CAP_LOAD) / 1000.0]
puts "\[INFO] Setting load to: $cap_load"
set_load $cap_load [all_outputs]

# -----------------------------------------------------------------------
# Clock constraints
# -----------------------------------------------------------------------
# Mux pin-to-pin skew (~2ns, TT 3.5 silicon measurement) adds to setup
# uncertainty on output paths.  Applied as -setup only — internal hold
# paths don't traverse the mux and must not pay this penalty.
set mux_skew 2.0
set base_uncertainty $::env(CLOCK_UNCERTAINTY_CONSTRAINT)
set setup_uncertainty [expr $base_uncertainty + $mux_skew]
puts "\[INFO] Setting clock uncertainty to: setup=$setup_uncertainty hold=$base_uncertainty"
set_clock_uncertainty -setup $setup_uncertainty $clocks
set_clock_uncertainty -hold $base_uncertainty $clocks

puts "\[INFO] Setting clock transition to: $::env(CLOCK_TRANSITION_CONSTRAINT)"
set_clock_transition $::env(CLOCK_TRANSITION_CONSTRAINT) $clocks

# -----------------------------------------------------------------------
# Timing derate
# -----------------------------------------------------------------------
puts "\[INFO] Setting timing derate to: $::env(TIME_DERATING_CONSTRAINT)%"
set_timing_derate -early [expr 1-[expr $::env(TIME_DERATING_CONSTRAINT) / 100]]
set_timing_derate -late [expr 1+[expr $::env(TIME_DERATING_CONSTRAINT) / 100]]

# -----------------------------------------------------------------------
# Clock propagation
# -----------------------------------------------------------------------
if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}
