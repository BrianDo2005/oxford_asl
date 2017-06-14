#!/usr/bin/env python
"""
Simple wxpython based GUI front-end to OXFORD_ASL command line tool

Currently this does not use any of the FSL python libraries. Possible improvements would be:
  - Use props library to hold run options and use the signalling mechanisms to communicate
    values. The built-in widget builder does not seem to be flexible enough however.
  - Use fsleyes embedded widget as the preview for a nicer, more interactive data preview

Requirements:
  - wxpython 
  - matplotlib
  - numpy
  - nibabel
"""

import sys
import os
import colorsys
import tempfile
import shutil
import traceback
import subprocess
import shlex

import wx
import wx.grid

import matplotlib
matplotlib.use('WXAgg')

from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure

import numpy as np
import nibabel as nib

class FslCmd():
    """
    An FSL command
    
    This will look for the executable in the same directory as the 
    GUI script first, then look in $FSLDIR/bin. This is to enable distribution
    of updated code as a bundle which can be run in-situ without installation
    """
    def __init__(self, cmd):
        localdir = os.path.dirname(os.path.abspath(__file__))
        if "FSLDIR" in os.environ: 
            fsldir = os.environ["FSLDIR"]
        else:
            fsldir = localdir
        if os.path.exists(os.path.join(localdir, cmd)):
            self.cmd = os.path.join(localdir, cmd)
        elif os.path.exists(os.path.join(fsldir, "bin/%s" % cmd)):
            self.cmd = os.path.join(fsldir, "bin/%s" % cmd)
        else:
            self.cmd = cmd
    
    def add(self, opt, val=None):
        if val is not None:
            self.cmd += " %s=%s" % (opt, str(val))
        else:
            self.cmd += " %s" % opt

    def write_output(self, line, out_widget=None):
        if out_widget is not None: 
            out_widget.AppendText(line)
            wx.Yield()
        else:
            sys.stdout.write(line)

    def run(self, out_widget=None):
        self.write_output(self.cmd, out_widget)
        args = shlex.split(self.cmd)
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while 1:
            retcode = p.poll() #returns None while subprocess is running
            line = p.stdout.readline()
            self.write_output(line, out_widget)
            if retcode is not None: break
        self.write_output("Return code: %i" % retcode, out_widget)
        
        return retcode

    def __str__(self): return self.cmd

class TabPage(wx.Panel):
    """
    Shared methods used by the various tab pages in the GUI
    """
    def __init__(self, parent, title, name=None):
        wx.Panel.__init__(self, parent=parent, id=wx.ID_ANY)
 
        self.sizer = wx.GridBagSizer(vgap=5, hgap=5)
        self.row = 0
        self.title = title
        if name is None:
            self.name = title.lower()
        else:
            self.name = name
            
    def pack(self, label, *widgets, **kwargs):
        """
        Add a horizontal line to the tab with a label and series of widgets

        If label is empty, first widget is used instead (usually to provide a checkbox)
        """
        col = 0
        border = kwargs.get("border", 10)
        font = self.GetFont()
        if "size" in kwargs:
            font.SetPointSize(kwargs["size"])
        if kwargs.get("bold", False):
            font.SetWeight(wx.BOLD)
        
        if label != "":
            text = wx.StaticText(self, label=label)
            text.SetFont(font)
            self.sizer.Add(text, pos=(self.row, col), border=border, flag=wx.ALIGN_CENTRE_VERTICAL | wx.LEFT)
            col += 1
        else:
            text = None

        for w in widgets:
            span = (1, 1)
            w.label = text
            if hasattr(w, "span"): span = (1, w.span)
            w.SetFont(font)
            w.Enable(col == 0 or kwargs.get("enable", True))
            self.sizer.Add(w, pos=(self.row, col), border=border, flag=wx.ALIGN_CENTRE_VERTICAL | wx.EXPAND | wx.LEFT, span=span)
            col += span[1]
        self.row += 1

    def file_picker(self, label, dir=False, handler=None, optional=False, initial_on=False, pack=True, **kwargs):
        """
        Add a file picker to the tab
        """
        if not handler: handler = self.update
        if dir: 
            picker = wx.DirPickerCtrl(self)
            picker.Bind(wx.EVT_DIRPICKER_CHANGED, handler)
        else: 
            picker = wx.FilePickerCtrl(self)
            picker.Bind(wx.EVT_FILEPICKER_CHANGED, handler)
        picker.span = 2
        if optional:
            cb = wx.CheckBox(self, label=label)
            cb.SetValue(initial_on)
            cb.Bind(wx.EVT_CHECKBOX, handler)
            picker.checkbox = cb
            if pack: self.pack("", cb, picker, enable=initial_on, **kwargs)
        elif pack:
            self.pack(label, picker, **kwargs)

        return picker

    def choice(self, label, choices, initial=0, optional=False, initial_on=False, handler=None, pack=True, **kwargs):
        """
        Add a widget to choose from a fixed set of options
        """
        if not handler: handler = self.update
        ch = wx.Choice(self, choices=choices)
        ch.SetSelection(initial)
        ch.Bind(wx.EVT_CHOICE, handler)
        if optional:
            cb = wx.CheckBox(self, label=label)
            cb.SetValue(initial_on)
            cb.Bind(wx.EVT_CHECKBOX, self.update)
            ch.checkbox = cb
            if pack: self.pack("", cb, ch, enable=initial_on, **kwargs)
        elif pack:
            self.pack(label, ch, **kwargs)
        return ch

    def number(self, label, handler=None, **kwargs):
        """
        Add a widget to choose a floating point number
        """
        if not handler: handler = self.update
        num = NumberChooser(self, changed_handler=handler, **kwargs)
        num.span = 2
        self.pack(label, num, **kwargs)
        return num

    def integer(self, label, handler=None, pack=True, **kwargs):
        """
        Add a widget to choose an integer
        """
        if not handler: handler = self.update
        spin = wx.SpinCtrl(self, **kwargs)
        spin.SetValue(kwargs.get("initial", 0))
        spin.Bind(wx.EVT_SPINCTRL, handler)
        if pack: self.pack(label, spin)
        return spin

    def checkbox(self, label, initial=False, handler=None, **kwargs):
        """
        Add a simple on/off option
        """
        cb = wx.CheckBox(self, label=label)
        cb.span=2
        cb.SetValue(initial)
        if handler: cb.Bind(wx.EVT_CHECKBOX, handler)
        else: cb.Bind(wx.EVT_CHECKBOX, self.update)
        self.pack("", cb, **kwargs)
        return cb

    def section(self, label):
        """
        Add a section heading
        """
        self.pack(label, bold=True)

    def update(self, evt=None):
        """
        Update the run module, i.e. when options have changed
        """
        if hasattr(self, "run"): 
            self.run.update()
            if hasattr(self, "preview"): self.preview.run = self.run

class PreviewPanel(wx.Panel):
    """
    Panel providing a simple image preview for the output of ASL_FILE.

    Used so user can check their choice of data grouping/ordering looks right
    """
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(300, 600))
        self.data = None
        self.run = None
        self.slice = -1
        self.nslices = 1
        self.view = 0
        self.figure = Figure(figsize=(3.5, 3.5), dpi=100, facecolor='black')
        self.axes = self.figure.add_subplot(111, axisbg='black')
        self.axes.get_xaxis().set_ticklabels([])
        self.axes.get_yaxis().set_ticklabels([])          
        self.canvas = FigureCanvas(self, -1, self.figure)
        self.canvas.mpl_connect('scroll_event', self.scroll)
        self.canvas.mpl_connect('button_press_event', self.view_change)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        font = self.GetFont()
        font.SetWeight(wx.BOLD)
        text = wx.StaticText(self, label="Data preview - perfusion weighted image")
        text.SetFont(font)
        self.sizer.AddSpacer(10)
        self.sizer.Add(text, 0)   
        self.sizer.Add(self.canvas, 2, border=5, flag = wx.EXPAND | wx.ALL)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(wx.StaticText(self, label="Use scroll wheel to change slice, double click to change view"), 0, flag=wx.ALIGN_CENTRE_VERTICAL)      
        self.update_btn = wx.Button(self, label="Update")
        self.update_btn.Bind(wx.EVT_BUTTON, self.update)
        hbox.Add(self.update_btn)
        self.sizer.Add(hbox)

        self.sizer.AddSpacer(10)
        text = wx.StaticText(self, label="Data order preview")
        text.SetFont(font)
        self.sizer.Add(text, 0)
        self.order_preview = AslDataPreview(self, 1, 1, True, "trp", True)
        self.sizer.Add(self.order_preview, 2, wx.EXPAND)
        self.SetSizer(self.sizer)
        self.Layout()

    def update(self, evt):
        """
        Update the preview. This is called explicitly when the user clicks the update
        button as it involves calling ASL_FILE and may be slow
        """
        self.data = None
        if self.run is not None:
            self.data = self.run.get_preview_data()
            # If multi-TI data, take mean over volumes
            if self.data is not None and len(self.data.shape) == 4:
                self.data = np.mean(self.data, axis=3)
                
        if self.data is not None:
            self.view = 0
            self.init_view()
        self.redraw()

    def init_view(self):
        self.nslices = self.data.shape[2-self.view]
        self.slice = self.nslices / 2
        self.redraw()

    def redraw(self):
        """
        Redraw the preview image
        """
        self.axes.clear() 
        if self.data is None: return

        if self.view == 0:
            sl = self.data[:,:,self.slice]
        elif self.view == 1:
            sl = self.data[:,self.slice,:]
        else:
            sl = self.data[self.slice,:,:]

        i = self.axes.imshow(sl.T, interpolation="nearest", vmin=sl.min(), vmax=sl.max())
        self.axes.set_ylim(self.axes.get_ylim()[::-1])
        i.set_cmap("gray")
        self.Layout()

    def view_change(self, event):
        """
        Called on mouse click event. Double click changes the view direction and redraws
        """
        if self.data is None: return
        if event.dblclick:
            self.view = (self.view + 1) % 3
            self.init_view()
            self.redraw()

    def scroll(self, event):
        """
        Called on mouse scroll wheel to move through the slices in the current view
        """
        if event.button == "up":
            if self.slice != self.nslices-1: self.slice += 1
        else:
            if self.slice != 0: self.slice -= 1
        self.redraw()
            
class AslRun(wx.Frame):
    """
    Determines the commands to run and displays them in a window
    """

    # The options we need to pass to oxford_asl for various data orderings
    order_opts = {"trp" : "--ibf=tis --iaf=diff", 
                  "trp,tc" : "--ibf=tis --iaf=tcb", 
                  "trp,ct" : "--ibf=tis --iaf=ctb",
                  "rtp" : "--ibf=rpt --iaf=diff",
                  "rtp,tc" : "--rpt --iaf=tcb",
                  "rtp,ct" : "--ibf=rpt --iaf=ctb",
                  "ptr,tc" : "--ibf=tis --iaf=tc",
                  "ptr,ct" : "--ibf=tis --iaf=ct",
                  "prt,tc" : "--ibf=rpt --iaf=tc",
                  "prt,ct" : "--ibf=rpt --iaf=ct"}

    def __init__(self, parent, run_btn, run_label):
        wx.Frame.__init__(self, parent, title="Run", size=(600, 400), style=wx.DEFAULT_FRAME_STYLE)

        self.run_btn = run_btn
        self.run_btn.Bind(wx.EVT_BUTTON, self.dorun)
        self.run_label = run_label
    
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.output_text = wx.TextCtrl(self, style=wx.TE_READONLY | wx.TE_MULTILINE)
        self.sizer.Add(self.output_text, 1, flag=wx.EXPAND)
            
        self.SetSizer(self.sizer)
        self.Bind(wx.EVT_CLOSE, self.close)

    def close(self, evt):
        self.Hide()

    def dorun(self, evt):
        if self.run_seq: 
            self.Show()
            self.Raise()
            self.output_text.Clear()
            for cmd in self.run_seq:
                cmd.run(self.output_text)  
                self.output_text.AppendText("\n")

    def update(self, evt=None):
        """
        Get the sequence of commands and enable the run button if options are valid. Otherwise
        display the first error in the status label
        """
        self.run_seq = None
        try:
            self.run_seq = self.get_run_sequence()
            self.run_label.SetForegroundColour(wx.Colour(0, 128, 0))
            self.run_label.SetLabel("Ready to Go")
            self.run_btn.Enable(True)
        except Exception, e:
            self.run_btn.Enable(False)
            self.run_label.SetForegroundColour(wx.Colour(255, 0, 0))
            self.run_label.SetLabel(str(e))

    def check_exists(self, label, file):
        if not os.path.exists(file):
            raise RuntimeError("%s - no such file or directory" % label)

    def get_preview_data(self):
        """
        Run ASL_FILE for perfusion weighted image - just for the preview
        """
        tempdir = tempfile.mkdtemp()
        self.preview_data = None
        try:
            meanfile = "%s/mean.nii.gz" % tempdir
            cmd = FslCmd("asl_file")
            cmd.add('--data="%s"' % self.input.data())
            cmd.add("--ntis=%i" % self.input.ntis())
            cmd.add('--mean="%s"' % meanfile)
            cmd.add(" ".join(self.get_data_order_options()))
            cmd.run()
            img = nib.load(meanfile)
            return img.get_data()
        except:
            traceback.print_exc()
            return None
        finally:
            shutil.rmtree(tempdir)

    def get_data_order_options(self):
        """
        Check data order is supported and return the relevant options
        """
        order, tagfirst = self.input.data_order()
        diff_opt = ""
        if self.input.tc_pairs(): 
            if tagfirst: order += ",tc"
            else: order += ",ct"
            diff_opt = "--diff"
        if order not in self.order_opts:
            raise RuntimeError("This data ordering is not supported by ASL_FILE")
        else: 
            return self.order_opts[order], diff_opt

    def get_run_sequence(self):
        """
        Get the sequence of commands for the selected options, throwing exception
        if any problems are found (e.g. files don't exist, mandatory options not specified)
        """
        run = []

        # Check input file exists, is an image and the TIs/repeats/TC pairs is consistent
        self.check_exists("Input data", self.input.data())
        img = nib.load(self.input.data())
        if len(img.shape) != 4:
            raise RuntimeError("Input data is not a 4D image")
        nvols = img.shape[3]

        N = self.input.ntis()
        if self.input.tc_pairs(): N *= 2
        if nvols % N != 0:
            self.input.nrepeats_label.SetLabel("<Unknown>")
            raise RuntimeError("Input data contains %i volumes - not consistent with %i TIs and TC pairs=%s" % (img.shape[3], self.input.ntis(), self.input.tc_pairs()))
        else:
            self.input.nrepeats_label.SetLabel("%i" % (nvols / N))
            self.preview.order_preview.n_tis = self.input.ntis()
            self.preview.order_preview.n_repeats = nvols / N
            self.preview.order_preview.tc_pairs = self.input.tc_pairs()
            self.preview.order_preview.tagfirst = self.input.tc_ch.GetSelection() == 0
            self.preview.order_preview.Refresh()

        # Create output dirs
        outdir = self.analysis.outdir()
        if outdir == "": 
            raise RuntimeError("Output directory not specified")

        # OXFORD_ASL
        cmd = FslCmd("oxford_asl")
        cmd.add(' -i "%s"' % self.input.data())
        cmd.add('-o "%s"' % outdir)
        cmd.add(self.get_data_order_options()[0])
        cmd.add("--tis %s" % ",".join(["%.2f" % v for v in self.input.tis()]))
        cmd.add("--bolus %s" % ",".join(["%.2f" % v for v in self.input.bolus_dur()]))
        if self.analysis.wp(): 
            cmd.add("--wp")
        else: 
            cmd.add("--t1 %.2f" % self.analysis.t1())
            cmd.add("--bat %.2f" % self.analysis.bat())
        cmd.add("--t1b %.2f" % self.analysis.t1b())
        cmd.add("--alpha %.2f" % self.analysis.ie())
        cmd.add("--spatial=%i" % int(self.analysis.spatial()))
        cmd.add("--fixbolus=%i" % int(self.analysis.fixbolus()))
        cmd.add("--mc=%i" % int(self.analysis.mc()))
        if self.analysis.infer_t1(): cmd.add("--infert1")
        if self.analysis.pv(): cmd.add("--pvcorr")
        if not self.analysis.macro(): cmd.add("--artoff")
        if self.analysis.mask() is not None:
            self.check_exists("Analysis mask", self.analysis.mask())
            cmd.add('-m "%s"' % self.analysis.mask())
        if self.input.labelling() == 1: 
            cmd.add("--casl")
        if self.analysis.transform():
            if self.analysis.transform_type() == 0:
                self.check_exists("Transformation matrix", self.analysis.transform_file())
                cmd.add('--asl2struc "%s"' % self.analysis.transform_file())
            elif self.analysis.transform_type() == 1:
                self.check_exists("Warp image", self.analysis.transform_file())
                cmd.add('--regfrom "%s"' % self.analysis.transform_file())
            else:
                pass # --fslanat already set when option 2 chosen

        # Structural image - may require Bet to be run
        fsl_anat_dir = self.input.fsl_anat()
        struc_image = self.input.struc_image()
        if fsl_anat_dir is not None:
            self.check_exists("FSL_ANAT", fsl_anat_dir)
            cmd.add('--fslanat="%s"' % fsl_anat_dir)
        elif struc_image is not None:
            self.check_exists("Structural image", struc_image)
            cp = FslCmd("imcp")
            cp.add('"%s"' % struc_image)
            cp.add('"%s/structural_head"' % outdir)
            run.append(cp)
            if self.input.struc_image_bet() == 1:
                bet = FslCmd("bet")
                bet.add('"%s"' % struc_image)
                bet.add('"%s/structural_brain"' % outdir)
                run.append(bet)
            else:
                struc_image_brain = self.input.struc_image_brain()
                self.check_exists("Structural brain image", struc_image_brain)
                cp = FslCmd("imcp")
                cp.add('"%s"' % struc_image_brain)
                cp.add('"%s/structural_brain"' % outdir)
                run.append(cp)
            cmd.add('--s "%s/structural_head"' % outdir)
            cmd.add('--sbrain "%s/structural_brain"' % outdir)
        else:
            # No structural image
            pass
    
        if self.input.readout() == 1:
            # 2D multi-slice readout - must give dt in seconds
            cmd.add("--slicedt %.5f" % (self.input.time_per_slice() / 1000))
            if self.input.multiband():
                cmd.add("--sliceband %i" % self.input.slices_per_band())

        # Distortion correction
        if self.distcorr.distcorr():
            if self.distcorr.distcorr_type() == 0:
                # Fieldmap
                self.check_exists("Fieldmap image", self.distcorr.fmap())
                cmd.add('--fmap="%s"' % self.distcorr.fmap())
                self.check_exists("Fieldmap magnitude image", self.distcorr.fmap_mag())
                if self.distcorr.fmap_be():
                    cmd.add('--fmapmagbrain="%s"' % self.distcorr.fmap_mag())
                else:
                    cmd.add('--fmapmag="%s"' % self.distcorr.fmap_mag())
            else:
                if self.distcorr.cblip(): cmd.add("--cblip")
            cmd.add("--echospacing=%.5f" % self.distcorr.echosp())
            cmd.add("--pedir=%s" % self.distcorr.pedir())
            
        # Calibration - do this via oxford_asl rather than calling asl_calib separately
        if self.calibration.calib():
            self.check_exists("Calibration image", self.calibration.calib_image())
            cmd.add('-c "%s"' % self.calibration.calib_image())
            if self.calibration.m0_type() == 0:
                #calib.add("--mode longtr")
                cmd.add("--tr %.2f" % self.calibration.seq_tr())
            else:
                raise RuntimeError("Saturation recovery not supported by oxford_asl")
                #calib.add("--mode satrevoc")
                #calib.add("--tis %s" % ",".join([str(v) for v in self.input.tis()]))
                # FIXME change -c option in sat recov mode?

            cmd.add("--cgain %.2f" % self.calibration.calib_gain())
            if self.calibration.calib_mode() == 0:
                cmd.add("--cmethod single")
                cmd.add("--tissref %s" % self.calibration.ref_tissue_type_name().lower())
                cmd.add("--te %.2f" % self.calibration.seq_te())
                cmd.add("--t1csf %.2f" % self.calibration.ref_t1())
                cmd.add("--t2csf %.2f" % self.calibration.ref_t2())
                cmd.add("--t2bl %.2f" % self.calibration.blood_t2())
                if self.calibration.ref_tissue_mask() is not None:
                    self.check_exists("Calibration reference tissue mask", self.calibration.ref_tissue_mask())
                    cmd.add('--csf "%s"' % self.calibration.ref_tissue_mask())
                if self.calibration.coil_image() is not None:
                    self.check_exists("Coil sensitivity reference image", self.calibration.coil_image())
                    cmd.add('--cref "%s"' % self.calibration.coil_image())
            else:
                cmd.add("--cmethod voxel")
        
        run.append(cmd)
        return run

class AslCalibration(TabPage):
    """ 
    Tab page containing calibration options
    """

    def __init__(self, parent):
        TabPage.__init__(self, parent, "Calibration")

        self.calib_cb = self.checkbox("Enable Calibration", bold=True, handler=self.calib_changed)

        self.calib_image_picker = self.file_picker("Calibration Image")
        self.m0_type_ch = self.choice("M0 Type", choices=["Proton Density (long TR)", "Saturation Recovery"])

        self.seq_tr_num = self.number("Sequence TR (s)", min=0,max=10,initial=6)
        self.calib_gain_num = self.number("Calibration Gain", min=0,max=5,initial=1)
        self.calib_mode_ch = self.choice("Calibration mode", choices=["Reference Region", "Voxelwise"])

        self.section("Reference tissue")

        self.ref_tissue_type_ch = self.choice("Type", choices=["CSF", "WM", "GM", "None"], handler=self.ref_tissue_type_changed)
        self.ref_tissue_mask_picker = self.file_picker("Mask", optional=True)
        self.seq_te_num = self.number("Sequence TE (ms)", min=0,max=30,initial=0)
        self.blood_t2_num = self.number("Blood T2 (ms)", min=0,max=1000,initial=150, step=10)
        self.coil_image_picker = self.file_picker("Coil Sensitivity Image", optional=True)
        self.ref_t1_num = self.number("Reference T1 (s)", min=0,max=5,initial=4.3)
        self.ref_t2_num = self.number("Reference T2 (ms)", min=0,max=1000,initial=750, step=10)

        self.sizer.AddGrowableCol(2, 1)
        self.SetSizer(self.sizer)

    def calib(self): return self.calib_cb.IsChecked()
    def m0_type(self): return self.m0_type_ch.GetSelection()
    def seq_tr(self): return self.seq_tr_num.GetValue()
    def seq_te(self): return self.seq_te_num.GetValue()
    def calib_image(self): return self.calib_image_picker.GetPath()
    def calib_gain(self): return self.calib_gain_num.GetValue()
    def calib_mode(self): return self.calib_mode_ch.GetSelection()
    def ref_tissue_type(self): return self.ref_tissue_type_ch.GetSelection()
    def ref_tissue_type_name(self): return self.ref_tissue_type_ch.GetString(self.ref_tissue_type())
    def ref_tissue_mask(self): 
        if self.ref_tissue_mask_picker.checkbox.IsChecked():
            return self.ref_tissue_mask_picker.GetPath()
        else:
            return None
    def ref_t1(self): return self.ref_t1_num.GetValue()
    def ref_t2(self): return self.ref_t2_num.GetValue()
    def blood_t2(self): return self.blood_t2_num.GetValue()
    def coil_image(self): 
        if self.coil_image_picker.checkbox.IsChecked(): return self.coil_image_picker.GetPath()
        else: return None

    def ref_tissue_type_changed(self, event):
        if self.ref_tissue_type() == 0: # CSF
            self.ref_t1_num.SetValue(4.3)
            self.ref_t2_num.SetValue(750)
        elif self.ref_tissue_type() == 1: # WM
            self.ref_t1_num.SetValue(1.0)
            self.ref_t2_num.SetValue(50)
        elif self.ref_tissue_type() == 2: # GM
            self.ref_t1_num.SetValue(1.3)
            self.ref_t2_num.SetValue(100)
        self.update()

    def calib_changed(self, event):
        self.distcorr.calib_changed(self.calib())
        self.update()

    def wp_changed(self, wp):
        self.update()

    def update(self, event=None):
        enable = self.calib()
        self.m0_type_ch.Enable(enable)
        self.seq_tr_num.Enable(enable and self.m0_type() == 0)
        self.calib_image_picker.Enable(enable)
        self.calib_gain_num.Enable(enable)
        self.coil_image_picker.checkbox.Enable(enable)
        if self.analysis.wp(): self.calib_mode_ch.SetSelection(1)
        self.calib_mode_ch.Enable(enable and not self.analysis.wp())
        self.ref_tissue_type_ch.Enable(enable and self.calib_mode() == 0)
        self.ref_tissue_mask_picker.checkbox.Enable(enable and self.calib_mode() == 0)
        self.ref_tissue_mask_picker.Enable(enable and self.ref_tissue_mask_picker.checkbox.IsChecked() and self.calib_mode() == 0)
        self.coil_image_picker.checkbox.Enable(enable and self.calib_mode() == 0)
        self.coil_image_picker.Enable(enable and self.calib_mode() == 0 and self.coil_image_picker.checkbox.IsChecked())
        self.seq_te_num.Enable(enable and self.calib_mode() == 0)
        self.blood_t2_num.Enable(enable and self.calib_mode() == 0)
        self.ref_t1_num.Enable(enable and self.calib_mode() == 0)
        self.ref_t2_num.Enable(enable and self.calib_mode() == 0)
        TabPage.update(self)

class AslDistCorr(TabPage):
    """
    Tab page containing distortion correction options
    """

    def __init__(self, parent):
        TabPage.__init__(self, parent, "Distortion Correction", "distcorr")

        self.distcorr_choices = ["Fieldmap", "Calibration image"]

        self.section("Distortion Correction")

        self.distcorr_cb = wx.CheckBox(self, label="Apply distortion correction")
        self.distcorr_cb.Bind(wx.EVT_CHECKBOX, self.update)
        self.distcorr_ch = wx.Choice(self, choices=self.distcorr_choices[:1])
        self.distcorr_ch.SetSelection(0)
        self.distcorr_ch.Bind(wx.EVT_CHOICE, self.update)
        self.pack("", self.distcorr_cb, self.distcorr_ch, enable=False)

        self.echosp_num = self.number("Effective EPI echo spacing", min=0, max=10)
        self.pedir_ch = self.choice("Phase encoding direction", choices=["x", "y", "z", "-x", "-y", "-z"])
        
        # Fieldmap options
        self.fmap_picker = self.file_picker("Fieldmap image (in rad/s)")
        self.fmap_mag_picker = self.file_picker("Fieldmap magnitude image")
        self.fmap_mag_be_cb = self.checkbox("Magnitude image is brain extracted")
        
        # Calibration image options
        self.cblip_cb = self.checkbox("Phase-encode-reversed calibration image")
        
        self.sizer.AddGrowableCol(1, 1)
        #sizer.AddGrowableRow(5, 1)
        self.SetSizer(self.sizer)

    def distcorr(self): return self.distcorr_cb.IsChecked()
    def distcorr_type(self): return self.distcorr_ch.GetSelection()
    def fmap(self): return self.fmap_picker.GetPath()
    def fmap_mag(self): return self.fmap_mag_picker.GetPath()
    def fmap_mag_be(self): return self.fmap_mag_be_cb.IsChecked()
    def echosp(self): return self.echosp_num.GetValue()
    def pedir(self): return self.pedir_ch.GetStringSelection()
    def cblip(self): return self.cblip_cb.IsChecked()

    def update(self, event=None):
        self.distcorr_ch.Enable(self.distcorr())
        self.pedir_ch.Enable(self.distcorr())
        self.echosp_num.Enable(self.distcorr())
        fmap = self.distcorr() and self.distcorr_type() == 0
        cal = self.distcorr() and self.distcorr_type() == 1
        self.fmap_picker.Enable(fmap)
        self.fmap_mag_picker.Enable(fmap)
        self.fmap_mag_be_cb.Enable(fmap)
        self.cblip_cb.Enable(cal)
        TabPage.update(self)
        
    def calib_changed(self, enabled):
        """ If calibration enabled, add the calibration image option for distortion correction"""
        sel = self.distcorr_ch.GetSelection()
        if enabled: 
            choices = self.distcorr_choices
            sel = 1
        else: 
            choices = self.distcorr_choices[:1]
            sel = 0
        self.distcorr_ch.Enable(False)
        self.distcorr_ch.Clear()
        self.distcorr_ch.AppendItems(choices)
        self.distcorr_ch.SetSelection(sel)
        self.update()

class AslAnalysis(TabPage):
    """
    Tab page containing data analysis options
    """

    def __init__(self, parent):
        TabPage.__init__(self, parent, "Analysis")

        self.transform_choices = ["Matrix", "Warp image", "Use FSL_ANAT output"]

        self.distcorr_choices = ["Fieldmap", "Calibration image"]

        self.section("Registration")

        self.transform_cb = wx.CheckBox(self, label="Transform to standard space")
        self.transform_cb.Bind(wx.EVT_CHECKBOX, self.update)
        self.transform_ch = wx.Choice(self, choices=self.transform_choices)
        self.transform_ch.SetSelection(2)
        self.transform_ch.Bind(wx.EVT_CHOICE, self.update)
        self.transform_picker = wx.FilePickerCtrl(self)
        self.transform_picker.Bind(wx.EVT_FILEPICKER_CHANGED, self.update)
        self.pack("", self.transform_cb, self.transform_ch, self.transform_picker, enable=False)

        self.section("Basic analysis options")

        self.outdir_picker = self.file_picker("Output Directory", dir=True)
        self.mask_picker = self.file_picker("Brain Mask", optional=True)
        self.wp_cb = self.checkbox("Analysis which conforms to 'White Paper' (Alsop et al 2014)", handler=self.wp_changed)

        self.section("Initial parameter values")

        self.bat_num = self.number("Bolus arrival time (s)", min=0,max=2.5,initial=1.3)
        self.t1_num = self.number("T1 (s)", min=0,max=3,initial=1.3)
        self.t1b_num = self.number("T1b (s)", min=0,max=3,initial=1.65)
        self.ie_num = self.number("Inversion Efficiency", min=0,max=1,initial=0.85)
        
        self.section("Analysis Options")

        self.spatial_cb = self.checkbox("Adaptive spatial regularization on perfusion", initial=True)
        self.infer_t1_cb = self.checkbox("Incorporate T1 value uncertainty")
        self.macro_cb = self.checkbox("Include macro vascular component")
        self.fixbolus_cb = self.checkbox("Fix bolus duration", initial=True)

        self.pv_cb = self.checkbox("Partial Volume Correction")
        self.mc_cb = self.checkbox("Motion Correction (MCFLIRT)")

        self.sizer.AddGrowableCol(1, 1)
        #sizer.AddGrowableRow(5, 1)
        self.SetSizer(self.sizer)

    def transform(self): return self.transform_cb.IsChecked()
    def transform_type(self): return self.transform_ch.GetSelection()
    def transform_file(self): return self.transform_picker.GetPath()
    def outdir(self): return self.outdir_picker.GetPath()
    def mask(self): 
        if self.mask_picker.checkbox.IsChecked(): return self.mask_picker.GetPath()
        else: return None
    def wp(self): return self.wp_cb.IsChecked()
    def bat(self): return self.bat_num.GetValue()
    def t1(self): return self.t1_num.GetValue()
    def t1b(self): return self.t1b_num.GetValue()
    def ie(self): return self.ie_num.GetValue()
    def spatial(self): return self.spatial_cb.IsChecked()
    def infer_t1(self): return self.infer_t1_cb.IsChecked()
    def macro(self): return self.macro_cb.IsChecked()
    def fixbolus(self): return self.fixbolus_cb.IsChecked()
    def pv(self): return self.pv_cb.IsChecked()
    def mc(self): return self.mc_cb.IsChecked()

    def update(self, event=None):
        self.transform_ch.Enable(self.transform())
        self.transform_picker.Enable(self.transform() and self.transform_type() != 2)
        self.mask_picker.Enable(self.mask_picker.checkbox.IsChecked())
        self.t1_num.Enable(not self.wp())
        self.bat_num.Enable(not self.wp())
        TabPage.update(self)

    def wp_changed(self, event):
        if self.wp():
            self.t1_num.SetValue(1.65)
            self.bat_num.SetValue(0)
        else:
            self.t1_num.SetValue(1.3)
            self.bat_num.SetValue(1.3)
        self.calibration.update()
        self.update()

    def labelling_changed(self, pasl):
        if pasl:
            self.bat_num.SetValue(0.7)
            self.ie_num.SetValue(0.98)
        else:
            self.bat_num.SetValue(1.3)
            self.ie_num.SetValue(0.85)

    def fsl_anat_changed(self, enabled):
        """ If FSL_ANAT is selected, use it by default, otherwise do not allow it """
        sel = self.transform_ch.GetSelection()
        if enabled: 
            choices = self.transform_choices
            sel = 2
        else: 
            choices = self.transform_choices[:2]
            if sel == 2: sel = 0
        self.transform_ch.Enable(False)
        self.transform_ch.Clear()
        self.transform_ch.AppendItems(choices)
        self.transform_ch.SetSelection(sel)
        self.transform_ch.Enable(self.transform())

class AslInputOptions(TabPage):
    """
    Tab page containing input data options
    """

    def __init__(self, parent):
        TabPage.__init__(self, parent, "Input Data", "input")
 
        self.groups = ["PLDs", "Repeats", "Tag/Control pairs"]
        self.abbrevs = ["t", "r", "p"]

        self.section("Data contents")

        self.data_picker = self.file_picker("Input Image")
        self.ntis_int = self.integer("Number of PLDs", min=1,max=100,initial=1)
        self.nrepeats_label = wx.StaticText(self, label="<Unknown>")
        self.pack("Number of repeats", self.nrepeats_label)

        self.section("Data order")

        self.choice1 = wx.Choice(self, choices=self.groups)
        self.choice1.SetSelection(2)
        self.choice1.Bind(wx.EVT_CHOICE, self.update)
        self.choice2 = wx.Choice(self, choices=self.groups)
        self.choice2.SetSelection(0)
        self.choice2.Bind(wx.EVT_CHOICE, self.update)
        self.pack("Grouping order", self.choice1, self.choice2)
        self.tc_ch = self.choice("Tag control pairs", choices=["Tag then control", "Control then tag"], optional=True, initial_on=True)
        
        self.section("Acquisition parameters")

        self.labelling_ch = self.choice("Labelling", choices=["pASL", "cASL/pcASL"], initial=1, handler=self.labelling_changed)

        self.bolus_dur_ch = wx.Choice(self, choices=["Constant", "Variable"])
        self.bolus_dur_ch.SetSelection(0)
        self.bolus_dur_ch.Bind(wx.EVT_CHOICE, self.update)
        self.bolus_dur_num = NumberChooser(self, min=0, max=2.5, step=0.1, initial=1.8)
        self.bolus_dur_num.span = 2
        self.bolus_dur_num.spin.Bind(wx.EVT_SPINCTRLDOUBLE, self.bolus_dur_changed)
        self.bolus_dur_num.slider.Bind(wx.EVT_SLIDER, self.bolus_dur_changed)
        self.pack("Bolus duration (s)", self.bolus_dur_ch, self.bolus_dur_num)
        
        self.bolus_dur_list = NumberList(self, self.ntis())
        self.bolus_dur_list.span = 3
        self.bolus_dur_list.Bind(wx.grid.EVT_GRID_CELL_CHANGED, self.update)
        self.pack("Bolus durations (s)", self.bolus_dur_list, enable=False)

        self.ti_list = NumberList(self, self.ntis())
        self.ti_list.span=3
        self.ti_list.Bind(wx.grid.EVT_GRID_CELL_CHANGED, self.update)
        self.pack("PLDs (s)", self.ti_list)
        
        self.readout_ch = wx.Choice(self, choices=["3D (eg GRASE)", "2D multi-slice (eg EPI)"])
        self.readout_ch.SetSelection(0)
        self.readout_ch.Bind(wx.EVT_CHOICE, self.update)
        self.time_per_slice_num = NumberChooser(self, label="Time per slice (ms)", min=0, max=50, step=1, initial=10)
        self.time_per_slice_num.span=2
        self.pack("Readout", self.readout_ch, self.time_per_slice_num)
        self.time_per_slice_num.Enable(False)
        
        self.multiband_cb = wx.CheckBox(self, label="Multi-band")
        self.multiband_cb.Bind(wx.EVT_CHECKBOX, self.update)
        self.slices_per_band_spin = wx.SpinCtrl(self, min=1, max=100, initial=5)
        self.slices_per_band_label = wx.StaticText(self, label="slices per band")
        self.pack("", self.multiband_cb, self.slices_per_band_spin, self.slices_per_band_label, enable=False)
        self.multiband_cb.Enable(False)

        self.section("Structure")

        self.fsl_anat_picker = self.file_picker("Use FSL_ANAT output", dir=True, optional=True, initial_on=True, handler=self.fsl_anat_changed)
        self.struc_image_picker = self.file_picker("Use Structural Image", optional=True)
        self.struc_image_ch = wx.Choice(self, choices=["Have brain image", "Run BET to extract brain"])
        self.struc_image_ch.Bind(wx.EVT_CHOICE, self.update)
        self.struc_image_ch.SetSelection(0)
        self.struc_image_brain_picker = wx.FilePickerCtrl(self)
        self.struc_image_brain_picker.span = 2
        self.struc_image_brain_picker.Bind(wx.EVT_FILEPICKER_CHANGED, self.update)
        self.pack("Brain extraction", self.struc_image_ch, self.struc_image_brain_picker)

        self.sizer.AddGrowableCol(2, 1)
        self.SetSizer(self.sizer)

    def data(self): return self.data_picker.GetPath()
    def ntis(self): return self.ntis_int.GetValue()
    def data_order(self): return self.preview.order_preview.order, self.preview.order_preview.tagfirst
    def tc_pairs(self): return self.tc_ch.checkbox.IsChecked()
    def labelling(self): return self.labelling_ch.GetSelection()
    def bolus_dur_type(self): return self.bolus_dur_ch.GetSelection()
    def bolus_dur(self): 
        if self.bolus_dur_type() == 0: return [self.bolus_dur_num.GetValue(), ]
        else: return self.bolus_dur_list.GetValues()
    def tis(self): 
        tis = self.ti_list.GetValues()
        if self.labelling() == 1:
            # For pASL TI = bolus_dur + PLD
            bolus_durs = self.bolus_dur()
            if len(bolus_durs) == 1: bolus_durs *= self.ntis()
            tis = [pld+bd for pld,bd in zip(tis, bolus_durs)]
        return tis
    def readout(self): return self.readout_ch.GetSelection()
    def time_per_slice(self): return self.time_per_slice_num.GetValue()
    def multiband(self): return self.multiband_cb.IsChecked()
    def slices_per_band(self): return self.slices_per_band_spin.GetValue()
    def fsl_anat(self): 
        if self.fsl_anat_picker.checkbox.IsChecked(): return self.fsl_anat_picker.GetPath()
        else: return None
    def struc_image(self): 
        if self.struc_image_picker.checkbox.IsChecked() and not self.fsl_anat():
            return self.struc_image_picker.GetPath()
        else: return None
    def struc_image_brain(self): 
        if self.struc_image_picker.checkbox.IsChecked() and not self.fsl_anat() and self.struc_image_bet() == 0:
            return self.struc_image_brain_picker.GetPath()
        else: return None
    def struc_image_bet(self): return self.struc_image_ch.GetSelection()

    def update(self, event=None):
        self.ti_list.set_size(self.ntis())
        self.bolus_dur_list.set_size(self.ntis())

        self.time_per_slice_num.Enable(self.readout() != 0)
        self.multiband_cb.Enable(self.readout() != 0)
        self.slices_per_band_spin.Enable(self.multiband() and self.readout() != 0)
        self.slices_per_band_label.Enable(self.multiband() and self.readout() != 0)

        use_fsl_anat = self.fsl_anat_picker.checkbox.IsChecked()
        use_struc_image = self.struc_image_picker.checkbox.IsChecked()
        self.fsl_anat_picker.Enable(use_fsl_anat)
        self.struc_image_picker.checkbox.Enable(not use_fsl_anat)
        self.struc_image_ch.Enable(use_struc_image and not use_fsl_anat)
        self.struc_image_picker.Enable(use_struc_image and not use_fsl_anat)
        self.struc_image_brain_picker.Enable(use_struc_image and not use_fsl_anat and self.struc_image_bet() == 0)
        self.struc_image_brain_picker.label.Enable(use_struc_image and not use_fsl_anat and self.struc_image_bet() == 0)
        
        self.bolus_dur_num.Enable(self.bolus_dur_type() == 0)
        self.bolus_dur_list.Enable(self.bolus_dur_type() == 1)

        self.tc_ch.Enable(self.tc_pairs())
        self.update_groups()

        TabPage.update(self)

    def labelling_changed(self, event):
        if event.GetInt() == 0:
            self.bolus_dur_num.SetValue(0.7)
            self.ntis_int.label.SetLabel("Number of TIs")
            self.ti_list.label.SetLabel("TIs")
            self.preview.order_preview.tis_name="TIs"
            self.groups[0] = "TIs"
        else:
            self.bolus_dur_num.SetValue(1.8)
            self.ntis_int.label.SetLabel("Number of PLDs")
            self.ti_list.label.SetLabel("PLDs")
            self.preview.order_preview.tis_name="PLDs"
            self.groups[0] = "PLDs"
        self.analysis.labelling_changed(event.GetInt() == 0)
        self.update()

    def fsl_anat_changed(self, event):
        self.analysis.fsl_anat_changed(self.fsl_anat_picker.checkbox.IsChecked())
        self.update()

    def bolus_dur_changed(self, event):
        """ If constant bolus duration is changed, update the disabled list of
            bolus durations to match, to avoid any confusion """
        if self.bolus_dur_type() == 0:
            for c in range(self.bolus_dur_list.n): 
                self.bolus_dur_list.SetCellValue(0, c, str(self.bolus_dur()[0]))
        event.Skip()
        
    def update_groups(self, group1=True, group2=True):
        g2 = self.choice2.GetSelection()
        g1 = self.choice1.GetSelection()
        if not self.tc_pairs():
            if g1 == 2: g1 = 0
            if g2 == 1: g2 = 0
            choices = 2
        else:
            choices = 3
        group1_items = []
        group2_items = []
        for idx, item in enumerate(self.groups[:choices]):
            group1_items.append(item)
            if idx != g1: group2_items.append(item)

        self.update_group_choice(self.choice1, group1_items, g1)
        self.update_group_choice(self.choice2, group2_items, g2)
        
        if g2 >= g1: g2 += 1
        order = self.abbrevs[g1]
        order += self.abbrevs[g2]
        order += self.abbrevs[3-g1-g2]
        self.preview.order_preview.order = order

    def update_group_choice(self, w, items, sel):
        w.Enable(False)
        w.Clear()
        w.AppendItems(items)
        w.SetSelection(sel)
        w.Enable(True)

class NumberChooser(wx.Panel):
    """
    Widget for choosing a floating point number
    """

    def __init__(self, parent, label=None, min=0, max=1, initial=0.5, step=0.1, digits=2, changed_handler=None):
        super(NumberChooser, self).__init__(parent)
        self.min, self.orig_min, self.max, self.orig_max = min, min, max, max
        self.handler = changed_handler
        self.hbox=wx.BoxSizer(wx.HORIZONTAL)
        if label is not None:
            self.label = wx.StaticText(self, label=label)
            self.hbox.Add(self.label, proportion=0, flag=wx.ALIGN_CENTRE_VERTICAL)
        # Set a very large maximum as we want to let the user override the default range
        self.spin = wx.SpinCtrlDouble(self, min=0, max=100000, inc=step, initial=initial)
        self.spin.SetDigits(digits)
        self.spin.Bind(wx.EVT_SPINCTRLDOUBLE, self.spin_changed)
        self.slider = wx.Slider(self, value=initial, minValue=0, maxValue=100)
        self.slider.SetValue(100*(initial-self.min)/(self.max-self.min))
        self.slider.Bind(wx.EVT_SLIDER, self.slider_changed)
        self.hbox.Add(self.slider, proportion=1, flag=wx.EXPAND | wx.ALIGN_CENTRE_VERTICAL)
        self.hbox.Add(self.spin, proportion=0, flag=wx.EXPAND | wx.ALIGN_CENTRE_VERTICAL)
        self.SetSizer(self.hbox)

    def GetValue(self):
        return self.spin.GetValue()
        
    def SetValue(self, val):
        self.spin.SetValue(val)
        self.slider.SetValue(100*(val-self.min)/(self.max-self.min))
        
    def slider_changed(self, event):
        v = event.GetInt()
        val = self.min + (self.max-self.min)*float(v)/100
        self.spin.SetValue(val)
        if self.handler: self.handler(event)
        event.Skip()

    def spin_changed(self, event):
        """ If user sets the spin outside the current range, update the slider range
        to match. However if they go back inside the current range, revert to this for
        the slider"""
        val = event.GetValue()
        if val < self.min: 
            self.min = val
        elif val > self.orig_min:
            self.min = self.orig_min
        if val > self.max: 
            self.max = val
        elif val < self.orig_max:
            self.max = self.orig_max
        self.slider.SetValue(100*(val-self.min)/(self.max-self.min))
        if self.handler: self.handler(event)
        event.Skip()
        
class NumberList(wx.grid.Grid):
    """
    Widget for specifying a list of numbers
    """

    def __init__(self, parent, n, default=1.8):
        super(NumberList, self).__init__(parent, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, 0 )
        self.n=0
        self.default = default
        self.CreateGrid(1, 0)
        self.SetRowLabelSize(0)
        self.SetColLabelSize(0)
        self.set_size(n)
        self.Bind(wx.EVT_SIZE, self.on_size)

    def GetValues(self):
        try:
            return [float(self.GetCellValue(0, c)) for c in range(self.n)]
        except ValueError, e:
            raise RuntimeError("Non-numeric values in number list")
            
    def set_size(self, n):
        if self.n == 0: default = self.default
        else: default = self.GetCellValue(0, self.n-1)
        if n > self.n:
            self.AppendCols(n - self.n)
            for c in range(self.n, n): self.SetCellValue(0, c, str(default))
        elif n < self.n:
            self.DeleteCols(n, self.n-n)
        self.n = n
        self.resize_cols()

    def resize_cols(self):
        w, h = self.GetClientSize()
        cw = w / self.n
        for i in range(self.n):
            self.SetColSize(i, cw)

    def on_size(self, event):
        event.Skip()
        self.resize_cols()

class AslDataPreview(wx.Panel):
    """
    Widget to display a preview of the data ordering selected (i.e. how the volumes in a 4D
    dataset map to TIs, repeats and tag/control pairs)
    """

    def __init__(self, parent, n_tis, n_repeats, tc_pairs, order, tagfirst):
        wx.Panel.__init__(self, parent, size=wx.Size(300, 300))
        self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.n_tis = n_tis
        self.n_repeats = n_repeats
        self.tc_pairs = tc_pairs
        self.tagfirst = tagfirst
        self.order = order
        self.tis_name = "PLDs"

    def on_size(self, event):
        event.Skip()
        self.Refresh()

    def get_col(self, pos, ti):
        if ti: h = 170.0/255
        else: 
            h = 90.0/255
        s, v = 0.5, 0.95 - pos/2
        r,g,b = colorsys.hsv_to_rgb(h, s, v)
        return wx.Colour(int(r*255), int(g*255), int(b*255))

    def on_paint(self, event):
        w, h = self.GetClientSize()
        N = self.n_tis * self.n_repeats
        if self.tc_pairs: N *= 2
        dc = wx.AutoBufferedPaintDC(self)
        dc.Clear()

        leg_width = (w-100)/4
        leg_start = 50

        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        rect = wx.Rect(leg_start, 20, leg_width/4, 20)
        dc.GradientFillLinear(rect, self.get_col(0, True), self.get_col(1.0, True), wx.EAST)
        dc.DrawRectangleRect(rect)
        dc.DrawText(self.tis_name, leg_start+leg_width/3, 20)

        rect = wx.Rect(leg_start+leg_width, 20, leg_width/4, 20)
        dc.GradientFillLinear(rect, self.get_col(0, False), self.get_col(1.0, False), wx.EAST)
        dc.DrawRectangleRect(rect)
        dc.DrawText("Repeats", leg_start+4*leg_width/3, 20)

        if self.tc_pairs:
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRectangle(leg_start+leg_width*2, 20, leg_width/4, 20)
            dc.DrawText("Tag", leg_start+7*leg_width/3, 20)

            b = wx.Brush('black', wx.BDIAGONAL_HATCH)
            dc.SetBrush(b)
            dc.DrawRectangle(leg_start+leg_width*3, 20, leg_width/4, 20)
            dc.DrawText("Control", leg_start+10*leg_width/3, 20)

        dc.DrawRectangle(50, 50, w-100, h-100)
        dc.DrawRectangle(50, 50, w-100, h-100)
        dc.DrawText("0", 50, h-50)
        dc.DrawText(str(N), w-50, h-50)

        seq = [1,]
        for t in self.order[::-1]:
            temp = seq
            seq = []
            for i in temp:
                if t == "t":
                    seq += [i,] * self.n_tis
                elif t == "p":
                    if not self.tc_pairs:
                        seq.append(i)
                    elif self.tagfirst:
                        seq.append(i)
                        seq.append(i+1)
                    else:
                        seq.append(i+1)
                        seq.append(i)
                elif t == "r":
                    seq.append(i)
                    seq += [i+2,] * (self.n_repeats - 1)
        
        tistart = -1
        ti_sep = 1
        for idx, s in enumerate(seq):
            if s == 1 and tistart < 0: 
                tistart = idx
            elif s == 1:
                ti_sep = idx - tistart
                break

        bwidth = float(w - 100) / N
        x = 50
        pos = 0.0
        ti = 0
        d = 1.0/self.n_tis
        for idx, s in enumerate(seq):
            dc.SetPen(wx.TRANSPARENT_PEN)
            b = wx.Brush(self.get_col(pos, s in (1, 2)), wx.SOLID)
            dc.SetBrush(b)
            dc.DrawRectangle(int(x), 50, int(bwidth+1), h-100)

            if s in (2, 4):
                b = wx.Brush('black', wx.BDIAGONAL_HATCH)
                dc.SetBrush(b)
                dc.DrawRectangle(int(x), 50, int(bwidth+1), h-100)

            dc.SetPen(wx.Pen('black'))
            dc.DrawLine(int(x), 50, int(x), h-50)
            x += bwidth
            if (idx+1) % ti_sep == 0: 
                pos += d
                ti += 1
                if ti == self.n_tis: 
                    pos = 0
                    ti = 0

class AslGui(wx.Frame):
    """
    Main GUI window
    """

    def __init__(self):
        wx.Frame.__init__(self, None, title="Basil", size=(1200, 750), style=wx.DEFAULT_FRAME_STYLE)
        #wx.Frame.__init__(self, None, title="Basil", size=(1200, 700), style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)
        main_panel = wx.Panel(self)
        main_vsizer = wx.BoxSizer(wx.VERTICAL)

        banner = wx.Panel(main_panel, size=(-1, 80))
        banner.SetBackgroundColour((54, 122, 157))
        pix = wx.StaticBitmap(banner, -1, wx.Bitmap("banner.png", wx.BITMAP_TYPE_ANY))
        main_vsizer.Add(banner, 0, wx.EXPAND)

        hpanel = wx.Panel(main_panel)
        hsizer = wx.BoxSizer(wx.HORIZONTAL)
        notebook = wx.Notebook(hpanel, id=wx.ID_ANY, style=wx.BK_DEFAULT)
        hsizer.Add(notebook, 1, wx.ALL|wx.EXPAND, 5)
        self.preview = PreviewPanel(hpanel)
        hsizer.Add(self.preview, 1, wx.EXPAND)
        hpanel.SetSizer(hsizer)
        main_vsizer.Add(hpanel, 2, wx.EXPAND)

        self.run_panel = wx.Panel(main_panel)
        runsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.run_label = wx.StaticText(self.run_panel, label="Unchecked")
        self.run_label.SetFont(wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        runsizer.Add(self.run_label, 1, wx.EXPAND)
        self.run_btn = wx.Button(self.run_panel, label="Run")
        runsizer.Add(self.run_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        self.run_panel.SetSizer(runsizer)
        main_vsizer.Add(self.run_panel, 0, wx.EXPAND)
        self.run_panel.Layout()
        
        main_panel.SetSizer(main_vsizer)
        
        self.run = AslRun(self, self.run_btn, self.run_label)
        setattr(self.run, "preview", self.preview)
        tabs = [AslInputOptions(notebook),
                AslAnalysis(notebook),
                AslDistCorr(notebook),
                AslCalibration(notebook)]

        for tab in tabs:
            notebook.AddPage(tab, tab.title)
            setattr(tab, "run", self.run)
            setattr(tab, "preview", self.preview)
            setattr(self.run, tab.name, tab)
            setattr(self.preview, tab.name, tab)
            for tab2 in tabs:
                if tab != tab2: setattr(tab, tab2.name, tab2)
            tab.update()

        self.Layout()

if __name__ == '__main__':
    app = wx.App(redirect=False)
    top = AslGui()
    top.Show()
    app.MainLoop()

