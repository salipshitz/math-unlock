#!/usr/bin/env python3
"""Cocoa-only math lock for macOS — **focus finally fixed** (Monterey compatible).

Root cause: macOS won't send key events to a border-less window unless the
*application* is front-most.  Clicking did that manually.  Solution: call
`NSApp.activateIgnoringOtherApps_(True)` right after we show the window, then
`makeKeyAndOrderFront_` and `makeFirstResponder_`.  Now the caret blinks in
 the field immediately.

Additional fixes for Monterey:
- Use NSTextView instead of NSTextField for reliable input handling
- More aggressive focus and field editor management
- Force cursor visibility with explicit selection

Tested on macOS 14.5 with PyObjC 10.1 / Python 3.13.
"""
from __future__ import annotations
import random, AppKit
from Foundation import NSObject, NSTimer, NSString, NSRange

TOTAL_QUESTIONS = 3
FONT_BIG   = AppKit.NSFont.systemFontOfSize_(64)
FONT_MED   = AppKit.NSFont.systemFontOfSize_(56)
FONT_SMALL = AppKit.NSFont.systemFontOfSize_(24)
PREFIX = "Problems left before Zohar can waste her time on YouTube: "

OPS = [
    ('+',  lambda a, b: a + b),
    ('-',  lambda a, b: a - b),
    ('×',  lambda a, b: a * b),
    ('÷',  lambda a, b: a // b),  # integer division
]

def new_question():
    op, fn = random.choice(OPS)
    if op == '×':
        a, b = random.randint(1, 12), random.randint(1, 12)
    elif op == '÷':
        b = random.randint(1, 7)
        q = random.randint(1, 7)          # quotient
        a = b * q                         # ensures a ÷ b == integer
    else:
        a, b = random.randint(1, 20), random.randint(1, 20)
        
    return f"{a} {op} {b} =", fn(a, b)


class LockWindow(AppKit.NSWindow):
    def canBecomeKeyWindow(self):
        return True
    def canBecomeMainWindow(self):
        return True
    def acceptsFirstResponder(self):
        return True


class AnswerTextView(AppKit.NSTextView):
    """Custom text view that handles enter key and forces focus"""
    def initWithFrame_(self, frame):
        self = AppKit.NSTextView.initWithFrame_(self, frame)
        if self:
            self.setFont_(FONT_MED)
            self.setAlignment_(AppKit.NSCenterTextAlignment)
            self.setTextColor_(AppKit.NSColor.whiteColor())
            self.setBackgroundColor_(AppKit.NSColor.blackColor())
            self.setInsertionPointColor_(AppKit.NSColor.whiteColor())
            self.setSelectedTextAttributes_({
                AppKit.NSBackgroundColorAttributeName: AppKit.NSColor.darkGrayColor(),
                AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor()
            })
            self.setRichText_(False)
            self.setImportsGraphics_(False)
            self.setUsesFontPanel_(False)
            self.setUsesRuler_(False)
            self.setVerticallyResizable_(False)
            self.setHorizontallyResizable_(False)
            self.setFieldEditor_(True)
            self.setEditable_(True)
            self.setSelectable_(True)
            self.delegate = None
        return self
    
    def acceptsFirstResponder(self):
        return True
    
    def becomeFirstResponder(self):
        result = AppKit.NSTextView.becomeFirstResponder(self)
        if result:
            # Force cursor to appear at end of text
            text_length = len(self.string())
            self.setSelectedRange_(NSRange(text_length, 0))
        return result
    
    def keyDown_(self, event):
        key_code = event.keyCode()
        chars = event.characters()
        
        if key_code == 36:  # Enter key
            if self.delegate and hasattr(self.delegate, 'textViewDidPressEnter_'):
                self.delegate.textViewDidPressEnter_(self)
        elif chars and (chars.isdigit() or chars in '+-'):
            # Allow only numbers and basic math symbols
            AppKit.NSTextView.keyDown_(self, event)
        elif key_code == 51:  # Backspace
            AppKit.NSTextView.keyDown_(self, event)
        # Ignore other keys
    
    def insertText_(self, text):
        # Only allow digits and basic math symbols
        if isinstance(text, str) and (text.isdigit() or text in '+-'):
            AppKit.NSTextView.insertText_(self, text)
    
    def shouldChangeTextInRange_replacementString_(self, range, text):
        # Allow deletion (empty string) or digits/math symbols
        if not text or text.isdigit() or text in '+-':
            return True
        return False


class Delegate(NSObject):
    def applicationDidFinishLaunching_(self, _):
        screen = AppKit.NSScreen.mainScreen().frame()
        style  = AppKit.NSWindowStyleMaskBorderless
        self.window = LockWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            screen, style, AppKit.NSBackingStoreBuffered, False)
        self.window.setLevel_(AppKit.NSStatusWindowLevel + 1)
        self.window.setOpaque_(True)
        self.window.setBackgroundColor_(AppKit.NSColor.blackColor())

        # Presentation options (Force-Quit still allowed)
        hide = (AppKit.NSApplicationPresentationHideDock |
                AppKit.NSApplicationPresentationHideMenuBar |
                AppKit.NSApplicationPresentationDisableAppleMenu |
                AppKit.NSApplicationPresentationDisableProcessSwitching |
                AppKit.NSApplicationPresentationDisableHideApplication |
                AppKit.NSApplicationPresentationDisableSessionTermination)
        AppKit.NSApp.setPresentationOptions_(hide)

        content = self.window.contentView()

        # Question label
        self.q_label = AppKit.NSTextField.labelWithString_("")
        self.q_label.setFrame_(((0, 40), (screen.size.width, 100)))
        self.q_label.setFont_(FONT_BIG)
        self.q_label.setAlignment_(AppKit.NSCenterTextAlignment)
        self.q_label.setTextColor_(AppKit.NSColor.whiteColor())
        content.addSubview_(self.q_label)

        # Counter label
        self.counter = AppKit.NSTextField.labelWithString_("")
        self.counter.setFont_(FONT_SMALL)
        self.counter.setTextColor_(AppKit.NSColor.whiteColor())
        self.counter.setAlignment_(AppKit.NSRightTextAlignment)
        content.addSubview_(self.counter)

        # Answer text view with scroll view container
        scroll_frame = ((screen.size.width/2-150, screen.size.height/2-50), (300, 100))
        self.scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(scroll_frame)
        self.scroll_view.setHasVerticalScroller_(False)
        self.scroll_view.setHasHorizontalScroller_(False)
        self.scroll_view.setBorderType_(AppKit.NSBezelBorder)
        self.scroll_view.setBackgroundColor_(AppKit.NSColor.blackColor())
        
        # Create text view
        text_frame = self.scroll_view.contentView().bounds()
        self.ans_field = AnswerTextView.alloc().initWithFrame_(text_frame)
        self.ans_field.delegate = self
        
        self.scroll_view.setDocumentView_(self.ans_field)
        content.addSubview_(self.scroll_view)

        # Put app & window front-most and focus the field
        self.window.orderFrontRegardless()
        AppKit.NSApp.activateIgnoringOtherApps_(True)  # <- key call
        self.window.makeKeyAndOrderFront_(None)
        self.window.setInitialFirstResponder_(self.ans_field)
        
        # Multiple attempts to establish focus (needed for Monterey)
        self.establish_focus()
        
        # Fallback timer in all run-loop modes so ensureFocus_ actually fires
        timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.15, self, 'ensureFocus:', None, True)
        AppKit.NSRunLoop.mainRunLoop().addTimer_forMode_(timer,
            AppKit.NSRunLoopCommonModes)

        self.remaining = TOTAL_QUESTIONS
        self.next_q()

    def establish_focus(self):
        """Aggressive focus establishment for Monterey compatibility"""
        # Try multiple methods to establish focus
        self.window.makeFirstResponder_(self.ans_field)
        self.ans_field.setSelectedRange_(NSRange(0, 0))
        
        # Schedule delayed focus attempts
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.1, self, 'delayedFocus:', None, False)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.3, self, 'delayedFocus:', None, False)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, 'delayedFocus:', None, False)

    def delayedFocus_(self, timer):
        """Delayed focus attempt"""
        if self.window.firstResponder() != self.ans_field:
            self.window.makeFirstResponder_(self.ans_field)
            self.ans_field.setSelectedRange_(NSRange(0, 0))

    def ensureFocus_(self, timer):
        if self.window.firstResponder() != self.ans_field:
            self.window.makeFirstResponder_(self.ans_field)
            self.ans_field.setSelectedRange_(NSRange(0, 0))

    def textViewDidPressEnter_(self, textView):
        """Called when Enter is pressed in the text view"""
        self.check_answer()

    def check_answer(self):
        """Check the answer and handle response"""
        try:
            guess = int(self.ans_field.string().strip())
        except ValueError:
            self.flash_(False)
            self.ans_field.setString_("")
            self.establish_focus()
            return

        if guess == self.answer:
            self.remaining -= 1
            self.flash_(True)
            if self.remaining == 0:
                AppKit.NSApp.terminate_(None)
                return
            self.next_q()
        else:
            self.flash_(False)
            self.ans_field.setString_("")
            self.establish_focus()

    # Feedback flash
    def flash_(self, ok: bool):
        color = AppKit.NSColor.greenColor() if ok else AppKit.NSColor.redColor()
        self.window.setBackgroundColor_(color)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.35, self, 'resetColor:', None, False)
    def resetColor_(self, timer):
        self.window.setBackgroundColor_(AppKit.NSColor.blackColor())

    # Counter
    def update_counter(self):
        text = PREFIX + str(self.remaining)
        attr = {AppKit.NSFontAttributeName: FONT_SMALL}
        width = NSString.stringWithString_(text).sizeWithAttributes_(attr).width + 20
        screen = AppKit.NSScreen.mainScreen().frame()
        self.counter.setFrame_(((screen.size.width - width, screen.size.height - 40), (width, 30)))
        self.counter.setStringValue_(text)

    def next_q(self):
        q, self.answer = new_question()
        self.q_label.setStringValue_(q)
        self.ans_field.setString_("")
        self.update_counter()
        # Re-establish focus after each question
        self.establish_focus()

if __name__ == '__main__':
    AppKit.NSApplication.sharedApplication()
    AppKit.NSApp().setDelegate_(Delegate.alloc().init())
    AppKit.NSApp().run()