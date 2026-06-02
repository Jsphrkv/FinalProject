#nullable enable
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace ElevatorSim
{
    public partial class ElevatorForm : Form
    {
        private readonly Elevator _elevator;
        private const int TotalFloors = 4;

        // ── Logical state ─────────────────────────────────────────────────
        private int _currentFloor = 1;
        private ElevatorDirection _dir = ElevatorDirection.Idle;
        private bool _systemRunning = true;

        // ── Door state ────────────────────────────────────────────────────
        private bool _doorsOpen = false;
        private float _doorOpenPct = 0f;
        // Pending door open: set when DoorsOpened fires, applied once car arrives
        private bool _pendingDoorOpen = false;
        private bool _pendingDoorClose = false;
        private readonly System.Windows.Forms.Timer _doorAnimTimer;

        // ── Smooth car movement ───────────────────────────────────────────
        private float _carY = 0f;
        private float _targetCarY = 0f;
        private bool _carYInitialised = false;
        private readonly System.Windows.Forms.Timer _renderTimer;

        public ElevatorForm()
        {
            InitializeComponent();
            _elevator = new Elevator(TotalFloors);
            SubscribeToElevatorEvents();

            _doorAnimTimer = new System.Windows.Forms.Timer { Interval = 16 };
            _doorAnimTimer.Tick += DoorAnimTick;

            _renderTimer = new System.Windows.Forms.Timer { Interval = 16 };
            _renderTimer.Tick += RenderTick;
            _renderTimer.Start();
        }

        // ── Render tick: smooth car movement + pending door flush ───────
        // Uses a hybrid approach:
        //   • While far from target  → constant speed (pixels per frame) so the
        //     bulk of travel feels steady, like a real elevator cabin.
        //   • Within the final 60 px → ease-out lerp for a gentle deceleration
        //     as it arrives at the floor.
        private const float CarSpeedPxPerFrame = 3.5f;   // lower = slower travel
        private const float EaseZone = 60f;    // px from target where ease starts

        private void RenderTick(object? sender, EventArgs e)
        {
            if (!_carYInitialised) return;

            float diff = _targetCarY - _carY;
            float absDiff = Math.Abs(diff);

            if (absDiff > 0.8f)
            {
                float move;
                if (absDiff > EaseZone)
                {
                    // Constant-speed phase — feels like a real elevator
                    move = CarSpeedPxPerFrame * Math.Sign(diff);
                    // Don't overshoot into the ease zone in one step
                    if (Math.Abs(move) > absDiff - EaseZone)
                        move = (absDiff - EaseZone) * Math.Sign(diff);
                }
                else
                {
                    // Ease-out phase — gentle deceleration on arrival
                    move = diff * 0.07f;
                    // Enforce minimum movement so it doesn't drag on forever
                    if (Math.Abs(move) < 0.8f)
                        move = 0.8f * Math.Sign(diff);
                }

                _carY += move;
                GetShaftPanel()?.Invalidate();
            }
            else
            {
                if (absDiff > 0f)
                {
                    _carY = _targetCarY;
                    GetShaftPanel()?.Invalidate();
                }

                // Car has arrived — now apply any pending door command
                if (_pendingDoorOpen)
                {
                    _pendingDoorOpen = false;
                    _doorsOpen = true;
                    _doorAnimTimer.Start();
                    UpdateStatusLabels();
                }
                else if (_pendingDoorClose)
                {
                    _pendingDoorClose = false;
                    _doorsOpen = false;
                    _doorAnimTimer.Start();
                    UpdateStatusLabels();
                }
            }
        }

        // ── Door animation ────────────────────────────────────────────────
        private void DoorAnimTick(object? sender, EventArgs e)
        {
            const float step = 0.045f;
            bool done;
            if (_doorsOpen && _doorOpenPct < 1f)
            {
                _doorOpenPct = Math.Min(1f, _doorOpenPct + step);
                done = _doorOpenPct >= 1f;
            }
            else if (!_doorsOpen && _doorOpenPct > 0f)
            {
                _doorOpenPct = Math.Max(0f, _doorOpenPct - step);
                done = _doorOpenPct <= 0f;
            }
            else { done = true; }

            UpdateStatusLabels();
            GetShaftPanel()?.Invalidate();
            if (done) _doorAnimTimer.Stop();
        }

        // ── Compute target Y from floor number ────────────────────────────
        private void UpdateTargetCarY()
        {
            var panel = GetShaftPanel();
            if (panel == null) return;
            int H = panel.Height;
            int floorH = (H - 36 - 4) / TotalFloors;
            int carH = (int)(floorH * 0.82f);
            int yBase = 36 + (TotalFloors - _currentFloor) * floorH;
            _targetCarY = yBase + (floorH - carH) / 2f;
            if (!_carYInitialised) { _carY = _targetCarY; _carYInitialised = true; }
        }

        // ── Elevator events ───────────────────────────────────────────────
        private void SubscribeToElevatorEvents()
        {
            _elevator.FloorChanged += (_, e) => this.Invoke(() =>
            {
                _currentFloor = e.CurrentFloor;
                var d = GetCurrentFloorDisplay();
                if (d != null) d.Text = e.CurrentFloor.ToString();
                UpdateTargetCarY();     // smooth move starts
                UpdateStatusLabels();
            });

            _elevator.DirectionChanged += (_, e) => this.Invoke(() =>
            {
                _dir = e.Direction;
                UpdateStatusLabels();
            });

            _elevator.RequestAdded += (_, e) => this.Invoke(() =>
                HighlightFloorBtn(e.CurrentFloor, true));

            _elevator.ElevatorStopped += (_, _) => this.Invoke(UpdateStatusLabels);

            _elevator.DoorsOpened += (_, e) => this.Invoke(() =>
            {
                // Queue the open — RenderTick will apply it once _carY == _targetCarY
                _pendingDoorOpen = true;
                _pendingDoorClose = false;
                HighlightFloorBtn(e.CurrentFloor, false);
                UpdateStatusLabels();
            });

            _elevator.DoorsClosed += (_, _) => this.Invoke(() =>
            {
                // Queue the close the same way
                _pendingDoorClose = true;
                _pendingDoorOpen = false;
                UpdateStatusLabels();
            });
        }

        // ── Status labels ─────────────────────────────────────────────────
        private void UpdateStatusLabels()
        {
            var dir = GetStatusDirectionLabel();
            var door = GetStatusDoorLabel();

            if (dir != null)
                dir.Text = _dir switch
                {
                    ElevatorDirection.Up => "DIRECTION   ↑  UP",
                    ElevatorDirection.Down => "DIRECTION   ↓  DOWN",
                    _ => "DIRECTION   —  IDLE"
                };

            if (door != null)
            {
                bool opening = _pendingDoorOpen || (_doorsOpen && _doorOpenPct < 1f);
                bool closing = _pendingDoorClose || (!_doorsOpen && _doorOpenPct > 0f);

                if (opening) door.Text = $"DOOR STATUS   OPENING {(int)(_doorOpenPct * 100)}%";
                else if (_doorsOpen) door.Text = "DOOR STATUS   OPEN";
                else if (closing) door.Text = $"DOOR STATUS   CLOSING {(int)((1 - _doorOpenPct) * 100)}%";
                else door.Text = "DOOR STATUS   CLOSED";
            }

            bool idle = _dir == ElevatorDirection.Idle;
            bool carArrived = Math.Abs(_targetCarY - _carY) < 1f;
            GetOpenDoorButton()!.Enabled = _systemRunning && idle && !_doorsOpen && !_pendingDoorOpen && carArrived;
            GetCloseDoorButton()!.Enabled = _systemRunning && (_doorsOpen || _pendingDoorOpen);
            GetUpButton()!.Enabled = _systemRunning && idle && !_doorsOpen && carArrived && _currentFloor < TotalFloors;
            GetDownButton()!.Enabled = _systemRunning && idle && !_doorsOpen && carArrived && _currentFloor > 1;
        }

        private void HighlightFloorBtn(int floor, bool on)
        {
            var btns = GetFloorButtons();
            if (btns == null || floor < 1 || floor > TotalFloors) return;
            btns[floor - 1].BackColor = on
                ? Color.FromArgb(18, 155, 55)
                : Color.FromArgb(48, 68, 118);
        }

        // ── Form load ─────────────────────────────────────────────────────
        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);

            LayoutFloorButtons();
            ForceLayoutLcd();
            UpdateTargetCarY();

            var btns = GetFloorButtons();
            if (btns != null)
                foreach (var btn in btns)
                    btn.Click += (s, _) => { if (s is Button b && b.Tag is int f) _elevator.RequestFloor(f); };

            GetOpenDoorButton()!.Click += (_, _) => _elevator.ManualOpenDoors();
            GetCloseDoorButton()!.Click += (_, _) => _elevator.ManualCloseDoors();
            GetUpButton()!.Click += (_, _) => _elevator.MoveUp();
            GetDownButton()!.Click += (_, _) => _elevator.MoveDown();

            GetStartButton()!.Click += (_, _) =>
            {
                _systemRunning = true;
                _elevator.Resume();
                GetPauseButton()!.Text = "⏸  PAUSE";
                SetInputEnabled(true);
                UpdateStatusLabels();
            };
            GetPauseButton()!.Click += (_, _) =>
            {
                _systemRunning = !_systemRunning;
                if (_systemRunning)
                {
                    _elevator.Resume();
                    GetPauseButton()!.Text = "⏸  PAUSE";
                }
                else
                {
                    _elevator.Pause();
                    GetPauseButton()!.Text = "▶  RESUME";
                }
                SetInputEnabled(_systemRunning);
                UpdateStatusLabels();
            };
            GetStopButton()!.Click += (_, _) =>
            {
                _elevator.Pause();
                _systemRunning = false;
                _doorsOpen = false;
                _doorOpenPct = 0f;
                _pendingDoorOpen = false;
                _pendingDoorClose = false;
                _dir = ElevatorDirection.Idle;
                _doorAnimTimer.Stop();
                var fb = GetFloorButtons();
                if (fb != null) foreach (var b in fb) b.BackColor = Color.FromArgb(48, 68, 118);
                SetInputEnabled(false);
                GetShaftPanel()?.Invalidate();
                UpdateStatusLabels();
            };

            GetShaftPanel()!.Paint += (_, pe) => DrawShaft(pe.Graphics);
            GetShaftPanel()!.Resize += (_, _) => { _carYInitialised = false; UpdateTargetCarY(); };

            UpdateStatusLabels();
        }

        private void SetInputEnabled(bool en)
        {
            var btns = GetFloorButtons();
            if (btns != null) foreach (var b in btns) b.Enabled = en;
        }

        // ═════════════════════════════════════════════════════════════════
        // SHAFT DRAWING
        // ═════════════════════════════════════════════════════════════════
        private void DrawShaft(Graphics g)
        {
            var panel = GetShaftPanel();
            if (panel == null) return;
            int W = panel.Width, H = panel.Height;

            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.Clear(Color.FromArgb(232, 228, 218));

            using var titleFont = new Font("Arial", 13, FontStyle.Bold);
            g.DrawString("4-Story Building", titleFont, Brushes.Black, 10, 6);

            const int topOffset = 36, botPad = 4;
            int totalH = H - topOffset - botPad;
            int floorH = totalH / TotalFloors;
            int shaftW = Math.Max(80, (int)(W * 0.22f));
            int shaftLeft = (int)(W * 0.44f);
            int shaftRight = shaftLeft + shaftW;

            for (int floor = TotalFloors; floor >= 1; floor--)
            {
                int yTop = topOffset + (TotalFloors - floor) * floorH;
                g.DrawLine(new Pen(Color.FromArgb(110, 108, 98), 2), 0, yTop, W, yTop);

                using var bgBrush = new SolidBrush(Color.FromArgb(218, 214, 204));
                g.FillRectangle(bgBrush, 0, yTop + 1, shaftLeft, floorH - 2);
                g.FillRectangle(bgBrush, shaftRight, yTop + 1, W - shaftRight, floorH - 2);

                DrawFloorLabel(g, floor, 55, yTop, floorH); // 55 = left margin before corridor wall
                DrawLeftCorridor(g, shaftLeft, yTop, floorH);
                DrawRightCorridor(g, shaftRight, yTop, W, floorH, floor);
            }
            g.DrawLine(new Pen(Color.FromArgb(110, 108, 98), 2), 0, topOffset + totalH, W, topOffset + totalH);

            // Shaft walls + rails
            g.DrawLine(new Pen(Color.FromArgb(50, 55, 68), 3), shaftLeft, topOffset, shaftLeft, topOffset + totalH);
            g.DrawLine(new Pen(Color.FromArgb(50, 55, 68), 3), shaftRight, topOffset, shaftRight, topOffset + totalH);
            g.DrawLine(new Pen(Color.FromArgb(80, 88, 104), 2), shaftLeft + 7, topOffset, shaftLeft + 7, topOffset + totalH);
            g.DrawLine(new Pen(Color.FromArgb(80, 88, 104), 2), shaftRight - 7, topOffset, shaftRight - 7, topOffset + totalH);

            int carW = shaftW - 18;
            int carH = (int)(floorH * 0.82f);
            DrawCar(g, shaftLeft + 9, (int)_carY, carW, carH);
        }

        private static void DrawFloorLabel(Graphics g, int floor, int labelAreaW,
            int yTop, int floorH)
        {
            // labelAreaW = width of the left corridor area reserved for the label
            using var f1 = new Font("Arial", 8, FontStyle.Bold);
            using var f2 = new Font("Arial", 18, FontStyle.Bold);

            string word = "FLOOR";
            string num = floor.ToString();

            SizeF wSize = g.MeasureString(word, f1);
            SizeF nSize = g.MeasureString(num, f2);

            int totalH = (int)(wSize.Height + nSize.Height);
            int startY = yTop + (floorH - totalH) / 2;

            float wordX = (labelAreaW - wSize.Width) / 2f;
            float numX = (labelAreaW - nSize.Width) / 2f;

            g.DrawString(word, f1, Brushes.Black, wordX, startY);
            g.DrawString(num, f2, Brushes.Black, numX, startY + wSize.Height);
        }

        private static void DrawLeftCorridor(Graphics g, int shaftLeft, int yTop, int floorH)
        {
            int lEdge = 55, rEdge = shaftLeft - 4;
            g.FillRectangle(new SolidBrush(Color.FromArgb(208, 204, 194)), lEdge, yTop + 2, rEdge - lEdge, floorH - 4);

            int lx = lEdge + (rEdge - lEdge) / 2 + 28, ly = yTop + 5;
            g.FillRectangle(new SolidBrush(Color.FromArgb(255, 238, 140)), lx, ly, 20, 5);
            g.DrawRectangle(new Pen(Color.FromArgb(140, 120, 50), 1), lx, ly, 19, 4);

            int dW = 46, dH = (int)(floorH * 0.60f);
            int dX = rEdge - dW - 10, dY = yTop + floorH - dH - 2;
            g.FillRectangle(new SolidBrush(Color.FromArgb(105, 68, 32)), dX, dY, dW, dH);
            var dPen = new Pen(Color.FromArgb(60, 35, 10), 1);
            g.DrawRectangle(dPen, dX, dY, dW - 1, dH - 1);
            g.DrawLine(dPen, dX + dW / 2, dY + 3, dX + dW / 2, dY + dH - 3);
            g.DrawLine(dPen, dX + 3, dY + dH / 2, dX + dW - 4, dY + dH / 2);
            g.FillEllipse(new SolidBrush(Color.Goldenrod), dX + dW - 9, dY + dH / 2 - 3, 6, 6);

            int px = lEdge + 8, pyB = yTop + floorH - 2;
            g.FillRectangle(new SolidBrush(Color.FromArgb(135, 78, 36)), px, pyB - 12, 12, 10);
            g.FillEllipse(new SolidBrush(Color.FromArgb(32, 110, 32)), px - 5, pyB - 26, 22, 18);
            g.FillEllipse(new SolidBrush(Color.FromArgb(24, 88, 24)), px, pyB - 32, 14, 14);
        }

        private void DrawRightCorridor(Graphics g, int shaftRight, int yTop, int W, int floorH, int floor)
        {
            int lx = W - 30, ly = yTop + 6;
            g.FillRectangle(new SolidBrush(Color.FromArgb(255, 238, 140)), lx, ly, 16, 5);
            g.DrawRectangle(new Pen(Color.FromArgb(140, 120, 50), 1), lx, ly, 15, 4);
            DrawCallPanel(g, shaftRight + 6, yTop + floorH / 2 - 28, floor, _currentFloor, _dir);
        }

        private static void DrawCallPanel(Graphics g, int x, int y, int floor,
            int elevatorFloor, ElevatorDirection elevatorDir)
        {
            int panW = 30, btnH = 24, gap = 3;
            bool hasUp = floor < TotalFloors;
            bool hasDown = floor > 1;
            int panH = 6 + (hasUp ? btnH : 0) + (hasUp && hasDown ? gap : 0) + (hasDown ? btnH : 0);
            panH = Math.Max(panH, 28);

            g.FillRectangle(new SolidBrush(Color.FromArgb(155, 160, 175)), x, y, panW, panH);
            var pp = new Pen(Color.FromArgb(100, 105, 120), 1);
            g.DrawRectangle(pp, x, y, panW - 1, panH - 1);

            using var af = new Font("Arial", 8, FontStyle.Bold);

            // A button lights up when the elevator is AT or PASSING this floor in that direction
            bool upLit = hasUp && floor == elevatorFloor && elevatorDir == ElevatorDirection.Up;
            bool downLit = hasDown && floor == elevatorFloor && elevatorDir == ElevatorDirection.Down;

            int btnY = y + 3;
            if (hasUp)
            {
                var fill = upLit
                    ? new SolidBrush(Color.FromArgb(255, 200, 0))   // lit yellow
                    : new SolidBrush(Color.FromArgb(188, 192, 206)); // normal grey
                var arrow = upLit ? Brushes.Black : Brushes.DarkGray;
                g.FillRectangle(fill, x + 3, btnY, panW - 6, btnH);
                g.DrawRectangle(pp, x + 3, btnY, panW - 7, btnH - 1);
                g.DrawString("▲", af, arrow, x + 8, btnY + 4);
                btnY += btnH + gap;
            }
            if (hasDown)
            {
                var fill = downLit
                    ? new SolidBrush(Color.FromArgb(255, 200, 0))
                    : new SolidBrush(Color.FromArgb(188, 192, 206));
                var arrow = downLit ? Brushes.Black : Brushes.DarkGray;
                g.FillRectangle(fill, x + 3, btnY, panW - 6, btnH);
                g.DrawRectangle(pp, x + 3, btnY, panW - 7, btnH - 1);
                g.DrawString("▼", af, arrow, x + 8, btnY + 4);
            }
        }

        private void DrawCar(Graphics g, int x, int y, int w, int h)
        {
            g.FillRectangle(new SolidBrush(Color.FromArgb(40, 0, 0, 0)), x + 4, y + 4, w, h);
            g.FillRectangle(new SolidBrush(Color.FromArgb(148, 156, 172)), x, y, w, h);
            g.DrawRectangle(new Pen(Color.FromArgb(72, 80, 100), 2), x, y, w, h);

            int dispH = Math.Max(20, h / 4);
            g.FillRectangle(new SolidBrush(Color.FromArgb(14, 18, 36)), x + 2, y + 2, w - 4, dispH);

            using var numFont = new Font("Courier New", 12, FontStyle.Bold);
            using var numBrush = new SolidBrush(Color.FromArgb(0, 220, 70));
            string numTxt = _currentFloor.ToString();
            SizeF ns = g.MeasureString(numTxt, numFont);
            g.DrawString(numTxt, numFont, numBrush,
                x + (w - ns.Width) / 2, y + 2 + (dispH - ns.Height) / 2);

            if (_dir != ElevatorDirection.Idle)
                g.DrawString(_dir == ElevatorDirection.Up ? "▲" : "▼",
                    new Font("Arial", 8, FontStyle.Bold),
                    new SolidBrush(Color.Yellow),
                    x + w - 14, y + 4);

            DrawDoors(g, x, y + dispH + 2, w, h - dispH - 4);
        }

        private void DrawDoors(Graphics g, int cx, int cy, int cw, int ch)
        {
            int halfW = cw / 2, singleW = halfW - 1;
            int offset = (int)(singleW * _doorOpenPct);

            if (offset > 0)
            {
                g.FillRectangle(new SolidBrush(Color.FromArgb(18, 22, 38)), cx + 2, cy, cw - 4, ch);
                g.FillRectangle(new SolidBrush(Color.FromArgb(30, 255, 255, 200)), cx + cw / 4, cy, cw / 2, ch);
                int lx = cx + 2 - offset, rx = cx + halfW + offset;
                g.FillRectangle(new SolidBrush(Color.FromArgb(118, 128, 148)), lx, cy, singleW, ch);
                DoorDetail(g, lx, cy, singleW, ch, true);
                g.FillRectangle(new SolidBrush(Color.FromArgb(118, 128, 148)), rx, cy, singleW, ch);
                DoorDetail(g, rx, cy, singleW, ch, false);
            }
            else
            {
                g.FillRectangle(new SolidBrush(Color.FromArgb(118, 128, 148)), cx + 2, cy, cw - 4, ch);
                g.DrawLine(new Pen(Color.FromArgb(70, 80, 100), 2), cx + halfW, cy, cx + halfW, cy + ch);
                int my = cy + ch / 2;
                g.FillEllipse(Brushes.Silver, cx + halfW - 9, my - 3, 7, 7);
                g.FillEllipse(Brushes.Silver, cx + halfW + 2, my - 3, 7, 7);
            }
        }

        private static void DoorDetail(Graphics g, int x, int y, int w, int h, bool isLeft)
        {
            g.DrawRectangle(new Pen(Color.FromArgb(160, 170, 192), 1), x, y, w - 1, h - 1);
            int hx = isLeft ? x + w - 8 : x + 6;
            g.FillEllipse(Brushes.Silver, hx - 3, y + h / 2 - 3, 7, 7);
        }

        // Called once on load and whenever the LCD panel needs immediate sizing
        private void ForceLayoutLcd()
        {
            var lcd = GetLcdContentPanel();
            if (lcd == null) return;
            // Give WinForms a chance to compute client sizes first
            lcd.PerformLayout();
            int w = lcd.ClientSize.Width;
            int h = lcd.ClientSize.Height;
            if (w <= 0 || h <= 0) return;

            int y = 4;
            int capH = Math.Max(16, (int)(h * 0.12f));
            int numH = Math.Max(50, (int)(h * 0.46f));
            int rowH = Math.Max(18, (int)(h * 0.17f));

            var cap = GetCurrentFloorDisplay();  // reuse label refs via existing accessors
            var dir = GetStatusDirectionLabel();
            var door = GetStatusDoorLabel();

            // cfCaption isn't exposed — find it by index (it's the first control added)
            if (lcd.Controls.Count >= 4)
            {
                lcd.Controls[0].SetBounds(0, y, w, capH); y += capH + 2;  // cfCaption
                cap?.SetBounds(0, y, w, numH); y += numH + 4;  // big number
                dir?.SetBounds(0, y, w, rowH); y += rowH + 2;  // direction
                door?.SetBounds(0, y, w, rowH);                             // door status
            }
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            base.OnFormClosed(e);
            _doorAnimTimer.Stop(); _doorAnimTimer.Dispose();
            _renderTimer.Stop(); _renderTimer.Dispose();
        }
    }
}