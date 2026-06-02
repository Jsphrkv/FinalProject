using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows.Forms;

namespace ElevatorSim
{
    public class ElevatorEventArgs : EventArgs
    {
        public int CurrentFloor { get; set; }
        public ElevatorDirection Direction { get; set; }
        public string Message { get; set; }
        public DateTime Timestamp { get; set; }

        public ElevatorEventArgs(int floor, ElevatorDirection direction, string message)
        {
            CurrentFloor = floor;
            Direction = direction;
            Message = message ?? string.Empty;
            Timestamp = DateTime.Now;
        }
    }

    public enum ElevatorDirection { Up, Down, Idle }

    /// <summary>
    /// SCAN elevator — re-evaluates best next stop every tick so intermediate
    /// floors added AFTER movement begins are still served on the way.
    /// </summary>
    public class Elevator
    {
        private int _currentFloor = 1;
        private ElevatorDirection _direction = ElevatorDirection.Idle;
        private readonly HashSet<int> _activeRequests = new();
        private readonly System.Windows.Forms.Timer _movementTimer;
        private readonly int _totalFloors;

        private bool _isMoving = false;
        private bool _doorsAreOpen = false;
        private bool _isPaused = false;

        public event EventHandler<ElevatorEventArgs>? FloorChanged;
        public event EventHandler<ElevatorEventArgs>? DirectionChanged;
        public event EventHandler<ElevatorEventArgs>? RequestAdded;
        public event EventHandler<ElevatorEventArgs>? ElevatorStopped;
        public event EventHandler<ElevatorEventArgs>? DoorsOpened;
        public event EventHandler<ElevatorEventArgs>? DoorsClosed;

        public int CurrentFloor => _currentFloor;
        public ElevatorDirection Direction => _direction;
        public int[] PendingRequests => _activeRequests.OrderBy(x => x).ToArray();

        public Elevator(int totalFloors = 4)
        {
            _totalFloors = totalFloors;
            _movementTimer = new System.Windows.Forms.Timer { Interval = 1500 };
            _movementTimer.Tick += MovementTimer_Tick;
        }

        public void RequestFloor(int floor)
        {
            if (floor < 1 || floor > _totalFloors) return;

            if (!_activeRequests.Contains(floor))
            {
                _activeRequests.Add(floor);
                OnRequestAdded(new ElevatorEventArgs(floor, _direction, $"Request added for floor {floor}"));
            }

            if (!_isPaused && !_isMoving && !_doorsAreOpen)
                ProcessNextRequest();
        }

        /// <summary>
        /// Manually open doors (only allowed when stopped at a floor).
        /// </summary>
        public void ManualOpenDoors()
        {
            if (_isMoving || _doorsAreOpen) return;
            _activeRequests.Remove(_currentFloor);
            OpenDoors();
        }

        /// <summary>
        /// Manually trigger door close (cancels auto-close timer by setting flag early).
        /// </summary>
        public void ManualCloseDoors()
        {
            if (!_doorsAreOpen) return;
            _doorsAreOpen = false;
            OnDoorsClosed(new ElevatorEventArgs(_currentFloor, _direction, $"Doors manually closed at floor {_currentFloor}"));
            if (!_isMoving)
                ProcessNextRequest();
        }

        public void MoveUp()
        {
            if (_isMoving || _doorsAreOpen) return;
            int target = _currentFloor + 1;
            if (target > _totalFloors) return;
            RequestFloor(target);
        }

        public void MoveDown()
        {
            if (_isMoving || _doorsAreOpen) return;
            int target = _currentFloor - 1;
            if (target < 1) return;
            RequestFloor(target);
        }

        public void Pause()
        {
            if (_isPaused) return;
            _isPaused = true;
            if (_isMoving)
            {
                _movementTimer.Stop();
            }
        }

        public void Resume()
        {
            if (!_isPaused) return;
            _isPaused = false;
            if (_activeRequests.Count > 0 && !_isMoving && !_doorsAreOpen)
            {
                ProcessNextRequest();
            }
            else if (_isMoving)
            {
                _movementTimer.Start();
            }
        }

        private void ProcessNextRequest()
        {
            if (_activeRequests.Count == 0)
            {
                if (_direction != ElevatorDirection.Idle)
                {
                    _direction = ElevatorDirection.Idle;
                    OnDirectionChanged(new ElevatorEventArgs(_currentFloor, _direction, "Elevator now idle"));
                }
                return;
            }

            int nextFloor = DetermineNextFloor();
            if (nextFloor == 0) return;

            if (nextFloor == _currentFloor)
            {
                _activeRequests.Remove(_currentFloor);
                OpenDoors();
                return;
            }

            ElevatorDirection newDir = nextFloor > _currentFloor
                ? ElevatorDirection.Up : ElevatorDirection.Down;

            if (_direction != newDir)
            {
                _direction = newDir;
                OnDirectionChanged(new ElevatorEventArgs(_currentFloor, _direction, $"Direction → {_direction}"));
            }

            _isMoving = true;
            _movementTimer.Start();
        }

        private void MovementTimer_Tick(object? sender, EventArgs e)
        {
            // KEY FIX: before moving, check if there's a stop on the current floor
            // (could happen if a request was added after movement began)
            if (_activeRequests.Contains(_currentFloor))
            {
                _movementTimer.Stop();
                _isMoving = false;
                _activeRequests.Remove(_currentFloor);
                OnElevatorStopped(new ElevatorEventArgs(_currentFloor, _direction, $"Stopped at floor {_currentFloor}"));
                OpenDoors();
                return;
            }

            // Move one floor
            if (_direction == ElevatorDirection.Up) _currentFloor++;
            else if (_direction == ElevatorDirection.Down) _currentFloor--;

            OnFloorChanged(new ElevatorEventArgs(_currentFloor, _direction, $"Reached floor {_currentFloor}"));

            // Re-evaluate: is this floor a stop? (handles requests added mid-travel)
            if (_activeRequests.Contains(_currentFloor))
            {
                _movementTimer.Stop();
                _isMoving = false;
                _activeRequests.Remove(_currentFloor);
                OnElevatorStopped(new ElevatorEventArgs(_currentFloor, _direction, $"Stopped at floor {_currentFloor}"));
                OpenDoors();
            }
            else
            {
                // Recalculate direction in case new requests were added
                int next = DetermineNextFloor();
                if (next != 0)
                {
                    ElevatorDirection newDir = next > _currentFloor ? ElevatorDirection.Up : ElevatorDirection.Down;
                    if (_direction != newDir)
                    {
                        _direction = newDir;
                        OnDirectionChanged(new ElevatorEventArgs(_currentFloor, _direction, $"Direction → {_direction}"));
                    }
                }
            }
        }

        /// <summary>
        /// SCAN: serve floors in current direction first, then reverse.
        /// When idle, go to nearest floor.
        /// </summary>
        private int DetermineNextFloor()
        {
            if (_activeRequests.Count == 0) return 0;

            var sorted = _activeRequests.OrderBy(x => x).ToList();

            if (_direction == ElevatorDirection.Up)
            {
                var above = sorted.Where(f => f > _currentFloor).ToList();
                if (above.Count > 0) return above.First();
                return sorted.Where(f => f < _currentFloor).DefaultIfEmpty(sorted.First()).Last();
            }

            if (_direction == ElevatorDirection.Down)
            {
                var below = sorted.Where(f => f < _currentFloor).ToList();
                if (below.Count > 0) return below.Last();
                return sorted.Where(f => f > _currentFloor).DefaultIfEmpty(sorted.Last()).First();
            }

            // Idle — nearest floor
            return sorted.OrderBy(f => Math.Abs(f - _currentFloor)).First();
        }

        private void OpenDoors()
        {
            _doorsAreOpen = true;
            OnDoorsOpened(new ElevatorEventArgs(_currentFloor, _direction, $"Doors opened at floor {_currentFloor}"));

            var closeTimer = new System.Windows.Forms.Timer { Interval = 5000 };
            closeTimer.Tick += (s, ev) =>
            {
                closeTimer.Stop();
                closeTimer.Dispose();
                if (!_doorsAreOpen) return; // already closed manually

                _doorsAreOpen = false;
                if (_activeRequests.Count == 0)
                {
                    _direction = ElevatorDirection.Idle;
                    OnDirectionChanged(new ElevatorEventArgs(_currentFloor, ElevatorDirection.Idle, "Elevator idle"));
                }
                OnDoorsClosed(new ElevatorEventArgs(_currentFloor, _direction, $"Doors closed at floor {_currentFloor}"));
                ProcessNextRequest();
            };
            closeTimer.Start();
        }

        protected virtual void OnFloorChanged(ElevatorEventArgs e) => FloorChanged?.Invoke(this, e);
        protected virtual void OnDirectionChanged(ElevatorEventArgs e) => DirectionChanged?.Invoke(this, e);
        protected virtual void OnRequestAdded(ElevatorEventArgs e) => RequestAdded?.Invoke(this, e);
        protected virtual void OnElevatorStopped(ElevatorEventArgs e) => ElevatorStopped?.Invoke(this, e);
        protected virtual void OnDoorsOpened(ElevatorEventArgs e) => DoorsOpened?.Invoke(this, e);
        protected virtual void OnDoorsClosed(ElevatorEventArgs e) => DoorsClosed?.Invoke(this, e);
    }
}