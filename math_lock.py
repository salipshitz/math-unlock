#!/usr/bin/env python3
"""Cocoa-only math lock for macOS — **focus finally fixed**.

Root cause: macOS won’t send key events to a border-less window unless the
*application* is front-most.  Clicking did that manually.  Solution: call
`NSApp.activateIgnoringOtherApps_(True)` right after we show the window, then
`makeKeyAndOrderFront_` and `makeFirstResponder_`.  Now the caret blinks in
 the field immediately.

Tested on macOS 14.5 with PyObjC 10.1 / Python 3.13.
"""
from __future__ import annotations
import random, AppKit
from Foundation import NSObject, NSTimer, NSString

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

        # Answer field
        self.ans_field = AppKit.NSTextField.alloc().initWithFrame_(((screen.size.width/2-150,
                                      screen.size.height/2-50), (300, 100)))
        self.ans_field.setEditable_(True)
        self.ans_field.setFont_(FONT_MED)
        self.ans_field.setAlignment_(AppKit.NSCenterTextAlignment)
        self.ans_field.setTextColor_(AppKit.NSColor.whiteColor())
        self.ans_field.setBackgroundColor_(AppKit.NSColor.blackColor())
        self.ans_field.setBezeled_(True)
        self.ans_field.setBezelStyle_(AppKit.NSTextFieldSquareBezel)
        content.addSubview_(self.ans_field)
        self.ans_field.setTarget_(self); self.ans_field.setAction_("check:")

        # Put app & window front-most and focus the field
        self.window.orderFrontRegardless()
        AppKit.NSApp.activateIgnoringOtherApps_(True)  # <- key call
        self.window.makeKeyAndOrderFront_(None)
        self.window.setInitialFirstResponder_(self.ans_field)
        self.window.makeFirstResponder_(self.ans_field)

        # Fallback timer in case launch animation steals focus
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.15, self, 'ensureFocus:', None, False)

        self.remaining = TOTAL_QUESTIONS
        self.next_q()

    def ensureFocus_(self, *_):
        if self.window.firstResponder() != self.ans_field:
            self.window.makeFirstResponder_(self.ans_field)

    # Feedback flash
    def flash_(self, ok: bool):
        color = AppKit.NSColor.greenColor() if ok else AppKit.NSColor.redColor()
        self.window.setBackgroundColor_(color)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.35, self, 'resetColor:', None, False)
    def resetColor_(self, *_):
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
        self.ans_field.setStringValue_("")
        self.update_counter()
        self.window.makeFirstResponder_(self.ans_field)

    # Enter pressed
    def check_(self, *_):
        try:
            guess = int(self.ans_field.stringValue().strip())
        except ValueError:
            self.flash_(False); self.ans_field.setStringValue_(""); return
        if guess == self.answer:
            self.remaining -= 1; self.flash_(True)
            if self.remaining == 0:
                AppKit.NSApp.terminate_(None); return
            self.next_q()
        else:
            self.flash_(False); self.ans_field.setStringValue_("")

if __name__ == '__main__':
    AppKit.NSApplication.sharedApplication()
    AppKit.NSApp().setDelegate_(Delegate.alloc().init())
    AppKit.NSApp().run()